from itertools import islice
from pathlib import Path
from typing import Optional

from amaranth import Array, C, Cat, Elaboratable, Module, Mux, Shape, Signal, signed
from amaranth.lib.enum import IntEnum
from amaranth.lib.io import Pin
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


class State(IntEnum, shape=1):
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

    plat_uart: Optional[Pin]

    state: Signal
    resolving: Signal
    fault_code: Signal
    fault_insn: Signal

    xreg: Array[Signal]
    xreg_written: Optional[Array[Signal]]
    pc: Signal
    insn: Signal

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

        self.xreg = Array(
            Signal(self.XLEN, init=self.reg_reset(xn)) for xn in range(self.XCOUNT)
        )
        if self.track_reg_written:
            self.xreg_written = Array(Signal() for _ in range(self.XCOUNT))

        self.pc = Signal(self.XLEN)
        self.insn = Signal(self.ILEN)

        self.wb_reg = Signal(range(self.XCOUNT))
        self.wb_val = Signal(self.XLEN)

        self.rb_reg1 = Signal(range(self.XCOUNT))
        self.rb_val1 = Signal(self.XLEN)
        self.rb_reg2 = Signal(range(self.XCOUNT))
        self.rb_val2 = Signal(self.XLEN)

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

        uart = self.uart = m.submodules.uart = UART(self.plat_uart)

        self.mmu = mmu = m.submodules.mmu = MMU(sysmem=self.sysmem, uart=uart)
        m.d.sync += mmu.read.ack.eq(0)

        m.d.comb += self.state.eq(State.RUNNING)

        m.d.sync += self.rb_val1.eq(self.xreg[self.rb_reg1]) # TODO: try these comb when we're not close to maxing out cells.
        m.d.sync += self.rb_val2.eq(self.xreg[self.rb_reg2])

        with m.FSM() as fsm:
            m.d.comb += self.resolving.eq(fsm.ongoing("fetch.resolve"))

            with m.State("fetch.init"):
                with m.If(self.wb_reg != 0):
                    m.d.sync += [
                        self.xreg[self.wb_reg].eq(self.wb_val),
                        self.wb_reg.eq(0),
                    ]
                    if self.track_reg_written:
                        m.d.sync += self.xreg_written[self.wb_reg].eq(1)
                m.d.sync += [
                    mmu.read.addr.eq(self.pc),
                    mmu.read.width.eq(AccessWidth.WORD),
                    mmu.read.ack.eq(1),
                ]
                m.next = "fetch.wait"

            with m.State("fetch.wait"):
                with m.If(mmu.read.valid):
                    insn = mmu.read.value
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
                            imm.eq(v_i.imm),
                            funct3.eq(v_i.funct3),
                            self.wb_reg.eq(v_i.rd),
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
                            imm.eq(v_i.imm),
                            funct3.eq(v_i.funct3),
                            self.wb_reg.eq(v_i.rd),
                        ]
                        m.next = "op.op_imm.wait"
                    with m.Case(Opcode.OP):
                        m.d.sync += [
                            self.read_xreg1(v_r.rs1),
                            self.read_xreg2(v_r.rs2),
                            funct3.eq(v_r.funct3),
                            funct7.eq(v_r.funct7),
                            self.wb_reg.eq(v_r.rd),
                        ]
                        m.next = "op.op.wait"
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
                            self.wb_reg.eq(v_i.rd),
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
                                        m.d.sync += self.xreg[1].eq(0x77774444)
                                    with m.Default():
                                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                            with m.Default():
                                self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.load.wait"):
                m.next = "op.load"
            with m.State("op.load"):
                addr = self.rb_val1 + imm[:12].as_signed()
                m.d.sync += [
                    mmu.read.addr.eq(addr),
                    mmu.read.width.eq(funct3[:2]),
                    mmu.read.ack.eq(1),
                ]
                with m.Switch(funct3):
                    with m.Case(OpLoadFunct.LW):
                        m.next = "lw.delay"
                    with m.Case(OpLoadFunct.LH):
                        m.next = "lh.delay"
                    with m.Case(OpLoadFunct.LHU):
                        m.next = "lhu.delay"
                    with m.Case(OpLoadFunct.LB):
                        m.next = "lb.delay"
                    with m.Case(OpLoadFunct.LBU):
                        m.next = "lbu.delay"
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.op_imm.wait"):
                m.next = "op.op_imm"
            with m.State("op.op_imm"):
                # sx I imm to XLEN
                v_sxi = Signal(signed(self.XLEN))
                m.d.comb += v_sxi.eq(imm[:12].as_signed())

                out = Signal(self.XLEN)
                m.d.sync += self.wb_val.eq(out)

                m.next = "fetch.init"
                with m.Switch(funct3):
                    with m.Case(OpImmFunct.ADDI):
                        m.d.comb += out.eq(self.rb_val1 + v_sxi)
                    with m.Case(OpImmFunct.SLTI):
                        m.d.comb += out.eq(self.rb_val1.as_signed() < v_sxi)
                    with m.Case(OpImmFunct.SLTIU):
                        m.d.comb += out.eq(self.rb_val1 < v_sxi.as_unsigned())
                    with m.Case(OpImmFunct.ANDI):
                        m.d.comb += out.eq(self.rb_val1 & v_sxi)
                    with m.Case(OpImmFunct.ORI):
                        m.d.comb += out.eq(self.rb_val1 | v_sxi)
                    with m.Case(OpImmFunct.XORI):
                        m.d.comb += out.eq(self.rb_val1 ^ v_sxi)
                    with m.Case(OpImmFunct.SLLI):
                        m.d.comb += out.eq(self.rb_val1 << imm[:5])
                    with m.Case(OpImmFunct.SRI):
                        rs1 = self.rb_val1
                        rs1 = Mux(imm[10], rs1.as_signed(), rs1)
                        m.d.comb += out.eq(rs1 >> imm[:5])
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.op.wait"):
                m.next = "op.op"
            with m.State("op.op"):
                m.d.sync += self.wb_val.eq(out)

                m.next = "fetch.init"
                with m.Switch(funct3):
                    with m.Case(OpRegFunct.ADDSUB):
                        m.d.comb += out.eq(Mux(
                            funct7[5],
                            self.rb_val1 - self.rb_val2,
                            self.rb_val1 + self.rb_val2,
                        ))
                    with m.Case(OpRegFunct.SLT):
                        m.d.comb += out.eq(self.rb_val1.as_signed() < self.rb_val2.as_signed())
                    with m.Case(OpRegFunct.SLTU):
                        m.d.comb += out.eq(self.rb_val1 < self.rb_val2)
                    with m.Case(OpRegFunct.AND):
                        m.d.comb += out.eq(self.rb_val1 & self.rb_val2)
                    with m.Case(OpRegFunct.OR):
                        m.d.comb += out.eq(self.rb_val1 | self.rb_val2)
                    with m.Case(OpRegFunct.XOR):
                        m.d.comb += out.eq(self.rb_val1 ^ self.rb_val2)
                    with m.Case(OpRegFunct.SLL):
                        m.d.comb += out.eq(self.rb_val1 << self.rb_val2[:5])
                    with m.Case(OpRegFunct.SR):
                        rs1 = self.rb_val1
                        rs1 = Mux(funct7[5], rs1.as_signed(), rs1)
                        m.d.comb += out.eq(rs1 >> self.rb_val2[:5])
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.store.wait"):
                m.next = "op.store"
            with m.State("op.store"):
                imm = Cat(v_s.imm4_0, v_s.imm11_5)
                addr = self.rb_val1 + imm.as_signed()
                m.d.sync += [
                    mmu.write.addr.eq(addr),
                    mmu.write.data.eq(self.rb_val2),
                    mmu.write.ack.eq(1),
                ]
                m.next = "s.delay"

                with m.Switch(v_s.funct3):
                    with m.Case(OpStoreFunct.SW):
                        m.d.sync += mmu.write.width.eq(AccessWidth.WORD)
                    with m.Case(OpStoreFunct.SH):
                        m.d.sync += mmu.write.width.eq(AccessWidth.HALF)
                    with m.Case(OpStoreFunct.SB):
                        m.d.sync += mmu.write.width.eq(AccessWidth.BYTE)
                    with m.Default():
                        self.fault(m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn)

            with m.State("op.branch.wait"):
                m.next = "op.branch"
            with m.State("op.branch"):
                imm = Cat(  # meow :3
                    C(0, 1), v_b.imm4_1, v_b.imm10_5, v_b.imm11, v_b.imm12
                ).as_signed()
                m.d.sync += self.pc.eq(self.pc + 4)
                m.next = "fetch.init"
                with m.Switch(v_b.funct3):
                    with m.Case(OpBranchFunct.BEQ):
                        with m.If(self.rb_val1 == self.rb_val2):
                            self.jump(m, self.pc + imm)
                    with m.Case(OpBranchFunct.BNE):
                        with m.If(self.rb_val1 != self.rb_val2):
                            self.jump(m, self.pc + imm)
                    with m.Case(OpBranchFunct.BLT):
                        with m.If(self.rb_val1.as_signed() < self.rb_val2.as_signed()):
                            self.jump(m, self.pc + imm)
                    with m.Case(OpBranchFunct.BGE):
                        with m.If(self.rb_val1.as_signed() >= self.rb_val2.as_signed()):
                            self.jump(m, self.pc + imm)
                    with m.Case(OpBranchFunct.BLTU):
                        with m.If(self.rb_val1 < self.rb_val2):
                            self.jump(m, self.pc + imm)
                    with m.Case(OpBranchFunct.BGEU):
                        with m.If(self.rb_val1 >= self.rb_val2):
                            self.jump(m, self.pc + imm)
                    with m.Default():
                        self.fault(
                            m, FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                        )

            with m.State("op.jalr.wait"):
                m.next = "op.jalr"
            with m.State("op.jalr"):
                m.next = "fetch.init"
                with self.jump(m, (self.rb_val1 + v_i.imm.as_signed()) & 0xFFFFFFFE):
                    m.d.sync += self.write_xreg(v_i.rd, self.pc)

            with m.State("lw.delay"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.wb_val.eq(mmu.read.value)
                    m.next = "fetch.init"

            with m.State("lh.delay"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.wb_val.eq(mmu.read.value[:16].as_signed())
                    m.next = "fetch.init"

            with m.State("lhu.delay"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.wb_val.eq(mmu.read.value[:16])
                    m.next = "fetch.init"

            with m.State("lb.delay"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.wb_val.eq(mmu.read.value[:8].as_signed())
                    m.next = "fetch.init"

            with m.State("lbu.delay"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.wb_val.eq(mmu.read.value[:8])
                    m.next = "fetch.init"

            with m.State("s.delay"):
                m.d.sync += mmu.write.ack.eq(0)
                with m.If(mmu.write.rdy):
                    # The one-cycle propagation delay here means we can count on
                    # the write being finished by the next read.
                    m.next = "fetch.init"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        m.d.sync += self.xreg[0].eq(0)

        return m

    def write_xreg(self, xn, value):
        return [
            self.wb_reg.eq(xn),
            self.wb_val.eq(value),
        ]

    def read_xreg1(self, xn):
        return self.rb_reg1.eq(xn)

    def read_xreg2(self, xn):
        return self.rb_reg2.eq(xn)

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
