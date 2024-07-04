from itertools import islice
from pathlib import Path
from typing import Optional

from amaranth import Array, C, Cat, Elaboratable, Module, Mux, Shape, Signal
from amaranth.lib.enum import Enum, IntEnum
from amaranth.lib.memory import Memory

from .mmu import MMU, AccessWidth
from .rv32 import (
    InsB,
    InsI,
    InsJ,
    InsR,
    InsS,
    InsU,
    OpBranchFunct,
    Opcode,
    OpImmFunct,
    OpLoadFunct,
    OpMiscMemFunct,
    OpRegFunct,
    OpStoreFunct,
    OpSystemFunct,
    Reg,
)
from .uart import UART

__all__ = ["Hart", "State", "FaultCode"]


class State(Enum, shape=1):
    RUNNING = 0
    FAULTED = 1


class FaultCode(IntEnum):
    UNSET = 0
    ILLEGAL_INSTRUCTION = 1
    PC_MISALIGNED = 2


class Hart(Elaboratable):
    ILEN = 32
    XLEN = 32
    XCOUNT = 32

    sysmem: Memory
    uart: UART
    reg_inits: dict[str, int]
    track_reg_written: bool

    plat_uart: Optional[object]

    state: Signal
    resolving: Signal
    fault_code: Signal
    fault_insn: Signal

    pc: Signal
    insn: Signal

    xmem: Memory
    xreg_written: Optional[Array[Signal]]
    xwr_en: Signal
    xwr_reg: Signal
    xwr_val: Signal

    xrd1_reg: Signal
    xrd1_val: Signal
    xrd2_reg: Signal
    xrd2_val: Signal

    def __init__(self, *, sysmem=None, reg_inits=None, track_reg_written=False):
        self.sysmem = sysmem or self.sysmem_for(
            Path(__file__).parent.parent.parent / "tests" / "test_shrimprw.bin",
            memory=8192,
        )
        self.reg_inits = reg_inits or {}
        if Reg.X1 not in self.reg_inits:
            self.reg_inits[Reg.X1] = 0xFFFF_FFFF  # ensure RET faults
        self.track_reg_written = track_reg_written

        self.plat_uart = None

        self.state = Signal(State)
        self.resolving = Signal()
        self.fault_code = Signal(FaultCode)
        self.fault_insn = Signal(self.ILEN)

        self.pc = Signal(self.XLEN)
        self.insn = Signal(self.ILEN)

        # TODO: don't allocate for x0. Probably cheaper just to take it though ..
        self.xmem = Memory(
            depth=self.XCOUNT,
            shape=self.XLEN,
            init=[self.reg_reset(xn) for xn in range(self.XCOUNT)],
        )
        if self.track_reg_written:
            self.xreg_written = Array(Signal() for _ in range(self.XCOUNT))

        self.xwr_en = Signal()
        self.xwr_reg = Signal(range(self.XCOUNT))
        self.xwr_val = Signal(self.XLEN)

        self.xrd1_reg = Signal(range(self.XCOUNT))
        self.xrd1_val = Signal(self.XLEN)
        self.xrd2_reg = Signal(range(self.XCOUNT))
        self.xrd2_val = Signal(self.XLEN)

    @classmethod
    def sysmem_for(cls, path, *, memory):
        init = cls.sysmem_init_for(path)
        return Memory(depth=memory // 2, shape=16, init=init)

    @staticmethod
    def sysmem_init_for(path):
        init = []
        it = iter(path.read_bytes())
        while batch := tuple(islice(it, 2)):
            match batch:
                case [a, b]:
                    init.append((b << 8) | a)
                case [e]:
                    init.append(e)
                case _:
                    raise RuntimeError("!?")
        return init

    def reg_reset(self, xn):
        if xn == 0:
            return 0
        if init := self.reg_inits.get(Reg[f"X{xn}"]):
            v = init
        elif xn == 2:  # SP
            v = (Shape.cast(self.sysmem.shape).width // 8) * self.sysmem.depth
        else:
            v = 0
        if v < 0:
            v += 2**self.XLEN
        return v

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.state.eq(State.RUNNING)

        self.mmu = mmu = m.submodules.mmu = MMU(sysmem=self.sysmem)
        self.uart = UART(self.plat_uart)
        mmu.peripherals.append(self.uart)

        m.d.comb += mmu.write.req.valid.eq(0)

        xmem = m.submodules.xmem = self.xmem
        # This ends up duplicating the RAM cells for both read ports.
        # TODO: read sequentially with one port.
        xmem_write = xmem.write_port()
        xmem_read1 = xmem.read_port()
        xmem_read2 = xmem.read_port()

        m.d.sync += self.xwr_en.eq(0)
        m.d.comb += [
            xmem_write.addr.eq(self.xwr_reg),
            xmem_write.data.eq(self.xwr_val),
            xmem_write.en.eq(self.xwr_en & self.xwr_reg.any()),

            xmem_read1.addr.eq(self.xrd1_reg),
            self.xrd1_val.eq(xmem_read1.data),
            xmem_read2.addr.eq(self.xrd2_reg),
            self.xrd2_val.eq(xmem_read2.data),
        ]

        if self.track_reg_written:
            with m.If(xmem_write.en):
                m.d.sync += self.xreg_written[xmem_write.addr].eq(1)

        with m.FSM() as fsm:
            m.d.comb += self.resolving.eq(fsm.ongoing("fetch.resolve"))

            # TODO: start next fetch as soon as a given instruction allows it.
            with m.State("fetch.init"):
                m.d.comb += [
                    mmu.read.req.payload.addr.eq(self.pc),
                    mmu.read.req.payload.width.eq(AccessWidth.WORD),
                    mmu.read.req.valid.eq(1),
                ]
                with m.If(mmu.read.req.ready):
                    m.next = "fetch.wait"

            with m.State("fetch.wait"):
                with m.If(mmu.read.resp.valid):
                    insn = mmu.read.resp.payload
                    m.d.sync += self.insn.eq(insn)

                    with m.If(~insn[:16].any() | insn.all()):
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                    with m.Else():
                        m.next = "fetch.resolve"

            with m.State("fetch.resolve"):
                insn = self.insn

                v_i = InsI(insn)
                v_u = InsU(insn)
                v_r = InsR(insn)
                v_j = InsJ(insn)
                v_b = InsB(insn)
                v_s = InsS(insn)

                # set pc/next before processing opcode so they can be
                # overridden, set x0 after so it remains zero (lol).
                m.next = "fetch.init"
                m.d.sync += self.pc.eq(self.pc + 4)

                imm = Signal(self.XLEN)
                funct3 = Signal(3)
                funct7 = Signal(7)

                with m.Switch(v_i.opcode):
                    with m.Case(Opcode.LOAD):
                        m.d.sync += [
                            self.read_xreg1(v_i.rs1),
                            imm.eq(v_i.imm.as_signed()),
                            funct3.eq(v_i.funct3),
                            self.xwr_reg.eq(v_i.rd),
                        ]
                        m.next = "op.load.wait"
                    with m.Case(Opcode.MISC_MEM):
                        with m.Switch(v_i.funct3):
                            with m.Case(OpMiscMemFunct.FENCE):
                                pass  # XXX no-op
                            with m.Default():
                                self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                    with m.Case(Opcode.OP_IMM):
                        m.d.sync += [
                            self.read_xreg1(v_i.rs1),
                            imm.eq(v_i.imm.as_signed()),
                            funct3.eq(v_i.funct3),
                            # funct7[0] never set by OP_IMM or OP; use to signal IMM to ALU.
                            funct7.eq(1),
                            self.xwr_reg.eq(v_i.rd),
                        ]
                        m.next = "alu.wait"
                    with m.Case(Opcode.OP):
                        m.d.sync += [
                            self.read_xreg1(v_r.rs1),
                            self.read_xreg2(v_r.rs2),
                            funct3.eq(v_r.funct3),
                            funct7.eq(v_r.funct7),
                            self.xwr_reg.eq(v_r.rd),
                        ]
                        m.next = "alu.wait"
                    with m.Case(Opcode.LUI):
                        m.d.sync += self.write_xreg(v_u.rd, v_u.imm << 12)
                    with m.Case(Opcode.AUIPC):
                        m.d.sync += self.write_xreg(v_u.rd, (v_u.imm << 12) + self.pc)
                    with m.Case(Opcode.STORE):
                        m.d.sync += [
                            self.read_xreg1(v_s.rs1),
                            self.read_xreg2(v_s.rs2),
                            imm.eq(Cat(v_s.imm4_0, v_s.imm11_5).as_signed()),
                            funct3.eq(v_s.funct3),
                        ]
                        m.next = "op.store.wait"
                    with m.Case(Opcode.BRANCH):
                        m.d.sync += [
                            self.pc.eq(self.pc),
                            self.read_xreg1(v_b.rs1),
                            self.read_xreg2(v_b.rs2),
                            imm.eq(Cat( # mew
                                C(0, 1), v_b.imm4_1, v_b.imm10_5, v_b.imm11, v_b.imm12,
                            ).as_signed()),
                            funct3.eq(v_b.funct3),
                        ]
                        m.next = "op.branch.wait"
                    with m.Case(Opcode.JALR):
                        m.d.sync += [
                            self.read_xreg1(v_i.rs1),
                            imm.eq(v_i.imm.as_signed()),
                            self.xwr_reg.eq(v_i.rd),
                        ]
                        m.next = "op.jalr.wait"
                    with m.Case(Opcode.JAL):
                        with self.jump(
                            m,
                            self.pc + Cat(C(0, 1), v_j.imm10_1, v_j.imm11, v_j.imm19_12, v_j.imm20).as_signed(),
                        ):
                            m.d.sync += self.write_xreg(v_j.rd, self.pc + 4)
                    with m.Case(Opcode.SYSTEM):
                        with m.Switch(v_i.funct3):
                            with m.Case(0):
                                with m.Switch(v_i.imm):
                                    with m.Case(OpSystemFunct.ECALL >> 3):
                                        m.d.sync += self.write_xreg(1, 0x1234CAFE)
                                    with m.Case(OpSystemFunct.EBREAK >> 3):
                                        m.d.sync += self.write_xreg(1, 0x77774444)
                                    with m.Default():
                                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                            with m.Default():
                                self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.load.wait"):
                m.next = "op.load"
            with m.State("op.load"):
                addr = self.xrd1_val + imm
                m.d.comb += [
                    mmu.read.req.payload.addr.eq(addr),
                    mmu.read.req.payload.width.eq(funct3[:2]),
                    mmu.read.req.valid.eq(1),
                ]
                m.next = "l.wait"

            with m.State("alu.wait"):
                m.next = "alu"
            with m.State("alu"):
                out = Signal(self.XLEN)
                m.d.sync += [
                    self.xwr_val.eq(out),
                    self.xwr_en.eq(1),
                ]

                alu_a = self.xrd1_val
                alu_b = Signal(self.XLEN)

                m.d.comb += alu_b.eq(self.xrd2_val)
                with m.If(funct7[0]):
                    m.d.comb += alu_b.eq(imm)
                with m.If(funct7[5]):
                    with m.If(funct3 == OpRegFunct.ADDSUB):
                        m.d.comb += alu_b.eq(-self.xrd2_val)
                    with m.Elif(funct3 == OpRegFunct.SR):
                        m.d.comb += alu_b.eq(Cat(self.xrd2_val[:5], C(0, 5), C(1, 1)))

                m.next = "fetch.init"
                with m.Switch(funct3):
                    with m.Case(OpImmFunct.ADDI):
                        m.d.comb += out.eq(alu_a + alu_b)
                    with m.Case(OpImmFunct.SLTI):
                        m.d.comb += out.eq(alu_a.as_signed() < alu_b.as_signed())
                    with m.Case(OpImmFunct.SLTIU):
                        m.d.comb += out.eq(alu_a < alu_b)
                    with m.Case(OpImmFunct.ANDI):
                        m.d.comb += out.eq(alu_a & alu_b)
                    with m.Case(OpImmFunct.ORI):
                        m.d.comb += out.eq(alu_a | alu_b)
                    with m.Case(OpImmFunct.XORI):
                        m.d.comb += out.eq(alu_a ^ alu_b)
                    with m.Case(OpImmFunct.SLLI):
                        m.d.comb += out.eq(alu_a << alu_b[:5])
                    with m.Case(OpImmFunct.SRI):
                        rs1 = Mux(alu_b[10], alu_a.as_signed(), alu_a)
                        m.d.comb += out.eq(rs1 >> alu_b[:5])
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.store.wait"):
                m.next = "op.store"
            with m.State("op.store"):
                addr = self.xrd1_val + imm
                m.d.comb += [
                    mmu.write.req.payload.addr.eq(addr),
                    mmu.write.req.payload.data.eq(self.xrd2_val),
                    mmu.write.req.valid.eq(1),
                ]
                with m.If(mmu.write.req.ready):
                    m.next = "s.wait"

                with m.Switch(funct3):
                    with m.Case(OpStoreFunct.SW):
                        m.d.comb += mmu.write.req.payload.width.eq(AccessWidth.WORD)
                    with m.Case(OpStoreFunct.SH):
                        m.d.comb += mmu.write.req.payload.width.eq(AccessWidth.HALF)
                    with m.Case(OpStoreFunct.SB):
                        m.d.comb += mmu.write.req.payload.width.eq(AccessWidth.BYTE)
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.branch.wait"):
                m.next = "op.branch"
            with m.State("op.branch"):
                taken = Signal()
                with m.If(taken):
                    self.jump(m, self.pc + imm)
                with m.Else():
                    m.d.sync += self.pc.eq(self.pc + 4)
                m.next = "fetch.init"

                with m.Switch(funct3):
                    with m.Case(OpBranchFunct.BEQ):
                        m.d.comb += taken.eq(self.xrd1_val == self.xrd2_val)
                    with m.Case(OpBranchFunct.BNE):
                        m.d.comb += taken.eq(self.xrd1_val != self.xrd2_val)
                    with m.Case(OpBranchFunct.BLT):
                        m.d.comb += taken.eq(self.xrd1_val.as_signed() < self.xrd2_val.as_signed())
                    with m.Case(OpBranchFunct.BGE):
                        m.d.comb += taken.eq(self.xrd1_val.as_signed() >= self.xrd2_val.as_signed())
                    with m.Case(OpBranchFunct.BLTU):
                        m.d.comb += taken.eq(self.xrd1_val < self.xrd2_val)
                    with m.Case(OpBranchFunct.BGEU):
                        m.d.comb += taken.eq(self.xrd1_val >= self.xrd2_val)
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.jalr.wait"):
                m.next = "op.jalr"
            with m.State("op.jalr"):
                m.next = "fetch.init"
                with self.jump(m, (self.xrd1_val + imm) & 0xFFFFFFFE):
                    m.d.sync += [
                        self.xwr_en.eq(1),
                        self.xwr_val.eq(self.pc),
                    ]

            with m.State("l.wait"):
                # Keep the address selected so the MMU knows where the request is routed.
                m.d.comb += mmu.read.req.payload.addr.eq(addr)

                with m.If(mmu.read.resp.valid):
                    p = mmu.read.resp.payload
                    val = Signal(self.XLEN)

                    m.d.sync += [
                        self.xwr_en.eq(1),
                        self.xwr_val.eq(val),
                    ]
                    m.next = "fetch.init"

                    with m.Switch(funct3):
                        with m.Case(OpLoadFunct.LW):
                            m.d.comb += val.eq(p)
                        with m.Case(OpLoadFunct.LH):
                            m.d.comb += val.eq(p[:16].as_signed())
                        with m.Case(OpLoadFunct.LHU):
                            m.d.comb += val.eq(p[:16])
                        with m.Case(OpLoadFunct.LB):
                            m.d.comb += val.eq(p[:8].as_signed())
                        with m.Case(OpLoadFunct.LBU):
                            m.d.comb += val.eq(p[:8])
                        with m.Default():
                            self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("s.wait"):
                # As above.
                m.d.comb += mmu.write.req.payload.addr.eq(addr)
                with m.If(mmu.write.req.ready):
                    # The one-cycle propagation delay here means we can count on
                    # the write being finished by the next read.
                    m.next = "fetch.init"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        return m

    def write_xreg(self, xn, value):
        return [
            self.xwr_en.eq(1),
            self.xwr_reg.eq(xn),
            self.xwr_val.eq(value),
        ]

    def read_xreg1(self, xn):
        return self.xrd1_reg.eq(xn)

    def read_xreg2(self, xn):
        return self.xrd2_reg.eq(xn)

    def jump(self, m, pc):
        with m.If(pc[:2].any()):
            self.fault(m, FaultCode.PC_MISALIGNED)
        with m.Else():
            m.d.sync += self.pc.eq(pc)
        # when used as contextmanager, statements in context only
        # occur if the jump didn't fault align
        return m.If(~pc[:2].any())

    def fault(self, m, code, *, insn=None):
        m.d.sync += self.fault_code.eq(code)
        if insn is not None:
            m.d.sync += self.fault_insn.eq(insn)
        m.next = "faulted"
