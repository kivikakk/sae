from itertools import islice
from pathlib import Path
from typing import Optional

from amaranth import (Array, C, Cat, Elaboratable, Module, Mux, ResetInserter,
                      Shape, Signal, signed)
from amaranth.lib.enum import IntEnum
from amaranth.lib.memory import Memory

from . import rv32
from .mmu import MMU, AccessWidth
from .rv32 import (InsB, InsI, InsJ, InsR, InsS, InsU, OpBranchFunct, Opcode,
                   OpImmFunct, OpLoadFunct, OpMiscMemFunct, OpRegFunct,
                   OpStoreFunct, OpSystemFunct, Reg)
from .uart import UART

__all__ = [
    "Top",
    "State",
    "FaultCode",
]


class State(IntEnum, shape=1):  # type: ignore
    RUNNING = 0
    FAULTED = 1


class FaultCode(IntEnum):
    UNSET = 0
    ILLEGAL_INSTRUCTION = 1
    PC_MISALIGNED = 2


class LsSize(IntEnum, shape=2):  # type: ignore
    B = 0
    H = 1
    W = 2


class Top(Elaboratable):
    ILEN = 32
    XLEN = 32
    XCOUNT = 32

    sysmem: Memory
    uart: UART
    reg_inits: Optional[dict[str, int]]
    track_reg_written: bool

    state: Signal
    fault_code: Signal
    fault_insn: Signal

    xreg: Array[Signal]
    xreg_written: Optional[Array[Signal]]
    pc: Signal
    insn: Signal

    def __init__(self, *, sysmem=None, reg_inits=None, track_reg_written=False):
        self.sysmem = sysmem or self.sysmem_for(
            Path(__file__).parent / "test_shrimprw.bin", memory=8192
        )
        self.reg_inits = reg_inits or {}
        if Reg.X1 not in self.reg_inits:
            self.reg_inits[Reg.X1] = 0xFFFF_FFFF  # ensure RET faults
        self.track_reg_written = track_reg_written

        self.state = Signal(State)
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
        from .. import icebreaker

        m = Module()

        match platform:
            case icebreaker():
                plat_uart = platform.request("uart")
                uart = self.uart = m.submodules.uart = UART(plat_uart)

            case _:
                uart = self.uart = m.submodules.uart = UART(None)

        self.mmu = mmu = m.submodules.mmu = MMU(
            sysmem=self.sysmem,
            uart=uart,
        )
        m.d.sync += mmu.read.ack.eq(0)

        m.d.comb += self.state.eq(State.RUNNING)

        with m.FSM():
            # Blowing everything ridiculously apart before we start getting a
            # pipeline going.
            with m.State("fetch.init"):
                with m.If(self.wb_reg != 0):
                    m.d.sync += [
                        self.xreg[self.wb_reg].eq(self.wb_val),
                        self.wb_reg.eq(0),
                    ]
                    if self.track_reg_written:
                        m.d.sync += self.xreg_written[self.wb_reg].eq(1)
                with m.If(self.pc[:2].any()):
                    m.d.sync += self.fault(FaultCode.PC_MISALIGNED)
                    m.next = "faulted"
                with m.Else():
                    m.d.sync += [
                        mmu.read.addr.eq(self.pc),
                        mmu.read.width.eq(AccessWidth.WORD),
                        mmu.read.ack.eq(1),
                    ]
                    m.next = "fetch.wait"

            with m.State("fetch.wait"):
                with m.If(mmu.read.valid):
                    m.d.sync += self.insn.eq(mmu.read.value)
                    m.next = "fetch.resolve"

            with m.State("fetch.resolve"):
                insn = self.insn
                assert len(insn) == self.ILEN
                with m.If((insn[:16] == 0) | (insn == C(1, 1).replicate(self.ILEN))):
                    m.d.sync += self.fault(FaultCode.ILLEGAL_INSTRUCTION, insn=insn)
                    m.next = "faulted"

                with m.Else():
                    v_i = InsI(insn)
                    v_u = InsU(insn)
                    v_r = InsR(insn)
                    v_j = InsJ(insn)
                    v_b = InsB(insn)
                    v_s = InsS(insn)

                    # sx I imm to XLEN
                    v_sxi = Signal(signed(32))
                    m.d.comb += v_sxi.eq(v_i.imm.as_signed())

                    # set pc/next before processing opcode so they can be
                    # overridden, set x0 after so it remains zero (lol).
                    m.next = "fetch.init"
                    m.d.sync += self.pc.eq(self.pc + 4)

                    with m.Switch(v_i.opcode):
                        with m.Case(Opcode.LOAD):
                            addr = self.xreg[v_i.rs1] + v_i.imm.as_signed()
                            m.d.sync += [
                                mmu.read.addr.eq(addr),
                                mmu.read.width.eq(v_i.funct3[:2]),
                                mmu.read.ack.eq(1),
                                self.wb_reg.eq(v_i.rd),
                            ]
                            with m.Switch(v_i.funct3):
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
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.MISC_MEM):
                            with m.Switch(v_i.funct3):
                                with m.Case(OpMiscMemFunct.FENCE):
                                    pass  # XXX no-op
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.OP_IMM):
                            with m.Switch(v_i.funct3):
                                with m.Case(OpImmFunct.ADDI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] + v_sxi
                                    )
                                with m.Case(OpImmFunct.SLTI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1].as_signed() < v_sxi
                                    )
                                with m.Case(OpImmFunct.SLTIU):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] < v_sxi.as_unsigned()
                                    )
                                with m.Case(OpImmFunct.ANDI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] & v_sxi
                                    )
                                with m.Case(OpImmFunct.ORI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] | v_sxi
                                    )
                                with m.Case(OpImmFunct.XORI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] ^ v_sxi
                                    )
                                with m.Case(OpImmFunct.SLLI):
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, self.xreg[v_i.rs1] << v_i.imm[:5]
                                    )
                                with m.Case(OpImmFunct.SRI):
                                    rs1 = self.xreg[v_i.rs1]
                                    rs1 = Mux(v_i.imm[10], rs1.as_signed(), rs1)
                                    m.d.sync += self.write_xreg(
                                        v_i.rd, rs1 >> v_i.imm[:5]
                                    )
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.OP):
                            with m.Switch(v_r.funct3):
                                with m.Case(OpRegFunct.ADDSUB):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd,
                                        Mux(
                                            v_r.funct7[5],
                                            self.xreg[v_r.rs1] - self.xreg[v_r.rs2],
                                            self.xreg[v_r.rs1] + self.xreg[v_r.rs2],
                                        ),
                                    )
                                with m.Case(OpRegFunct.SLT):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd,
                                        self.xreg[v_r.rs1].as_signed()
                                        < self.xreg[v_r.rs2].as_signed(),
                                    )
                                with m.Case(OpRegFunct.SLTU):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd, self.xreg[v_r.rs1] < self.xreg[v_r.rs2]
                                    )
                                with m.Case(OpRegFunct.AND):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd, self.xreg[v_r.rs1] & self.xreg[v_r.rs2]
                                    )
                                with m.Case(OpRegFunct.OR):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd, self.xreg[v_r.rs1] | self.xreg[v_r.rs2]
                                    )
                                with m.Case(OpRegFunct.XOR):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd, self.xreg[v_r.rs1] ^ self.xreg[v_r.rs2]
                                    )
                                with m.Case(OpRegFunct.SLL):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd,
                                        self.xreg[v_r.rs1] << self.xreg[v_r.rs2][:5],
                                    )
                                with m.Case(OpRegFunct.SR):
                                    m.d.sync += self.write_xreg(
                                        v_r.rd,
                                        Mux(
                                            v_r.funct7[5],
                                            self.xreg[v_r.rs1].as_signed(),
                                            self.xreg[v_r.rs1],
                                        )
                                        >> self.xreg[v_r.rs2][:5],
                                    )
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.LUI):
                            m.d.sync += self.write_xreg(v_u.rd, v_u.imm << 12)
                        with m.Case(Opcode.AUIPC):
                            m.d.sync += self.write_xreg(
                                v_u.rd, (v_u.imm << 12) + self.pc
                            )
                        with m.Case(Opcode.STORE):
                            imm = Cat(v_s.imm4_0, v_s.imm11_5)
                            addr = self.xreg[v_s.rs1] + imm.as_signed()
                            m.d.sync += [
                                mmu.write.addr.eq(addr),
                                mmu.write.data.eq(self.xreg[v_s.rs2]),
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
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.BRANCH):
                            # TODO: we're meant to raise
                            # instruction-address-misaligned if the target
                            # address isn't 4-byte aligned (modulo RVC) **iff**
                            # the condition evaluates to true.
                            imm = Cat(  # meow :3
                                C(0, 1), v_b.imm4_1, v_b.imm10_5, v_b.imm11, v_b.imm12
                            ).as_signed()
                            with m.Switch(v_b.funct3):
                                with m.Case(OpBranchFunct.BEQ):
                                    with m.If(self.xreg[v_b.rs1] == self.xreg[v_b.rs2]):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Case(OpBranchFunct.BNE):
                                    with m.If(self.xreg[v_b.rs1] != self.xreg[v_b.rs2]):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Case(OpBranchFunct.BLT):
                                    with m.If(
                                        self.xreg[v_b.rs1].as_signed()
                                        < self.xreg[v_b.rs2].as_signed()
                                    ):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Case(OpBranchFunct.BGE):
                                    with m.If(
                                        self.xreg[v_b.rs1].as_signed()
                                        >= self.xreg[v_b.rs2].as_signed()
                                    ):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Case(OpBranchFunct.BLTU):
                                    with m.If(self.xreg[v_b.rs1] < self.xreg[v_b.rs2]):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Case(OpBranchFunct.BGEU):
                                    with m.If(self.xreg[v_b.rs1] >= self.xreg[v_b.rs2]):
                                        m.d.sync += self.pc.eq(self.pc + imm)
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.JALR):
                            m.d.sync += [
                                self.write_xreg(v_i.rd, self.pc + 4),
                                self.pc.eq(
                                    (self.xreg[v_i.rs1] + v_i.imm.as_signed())
                                    & 0xFFFFFFFE
                                ),
                            ]
                        with m.Case(Opcode.JAL):
                            m.d.sync += [
                                self.write_xreg(v_j.rd, self.pc + 4),
                                self.pc.eq(
                                    self.pc
                                    + Cat(  # meow! :|3
                                        C(0, 1),
                                        v_j.imm10_1,
                                        v_j.imm11,
                                        v_j.imm19_12,
                                        v_j.imm20,
                                    ).as_signed()
                                ),
                            ]
                        with m.Case(Opcode.SYSTEM):
                            with m.Switch(v_i.funct3):
                                with m.Case(0):
                                    with m.Switch(v_i.imm):
                                        with m.Case(OpSystemFunct.ECALL >> 3):
                                            m.d.sync += self.write_xreg(1, 0x1234CAFE)
                                        with m.Case(OpSystemFunct.EBREAK >> 3):
                                            m.d.sync += self.xreg[1].eq(0x77774444)
                                        with m.Default():
                                            m.d.sync += self.fault(
                                                FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                            )
                                            m.next = "faulted"
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                                    )
                                    m.next = "faulted"
                        with m.Default():
                            m.d.sync += self.fault(
                                FaultCode.ILLEGAL_INSTRUCTION, insn=insn
                            )
                            m.next = "faulted"

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

    def fault(self, code, *, insn=None):
        assigns = [self.fault_code.eq(code)]
        if insn is not None:
            assigns.append(self.fault_insn.eq(insn))
        return assigns


class DeployedTop(Elaboratable):
    def __init__(self, *args, **kwargs):
        self.top = Top(*args, **kwargs)

    def elaborate(self, platform):
        from .. import icebreaker

        m = Module()

        rst = Signal()
        m.d.sync += rst.eq(0)

        match platform:
            case icebreaker():
                plat_button = platform.request("button")
                with m.If(plat_button.i):
                    m.d.sync += rst.eq(1)

        m.submodules.top = ResetInserter(rst)(self.top)

        return m
