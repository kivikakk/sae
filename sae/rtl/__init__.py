from typing import Optional

from amaranth import Array, C, Cat, Elaboratable, Module, Mux, Signal, signed
from amaranth.hdl import Memory, ReadPort, WritePort
from amaranth.lib.enum import IntEnum

from . import rv32
from .rv32 import (InsB, InsI, InsJ, InsR, InsS, InsU, OpBranchFunct, Opcode,
                   OpImmFunct, OpLoadFunct, OpMiscMemFunct, OpRegFunct,
                   OpStoreFunct)

__all__ = [
    "Top",
    "State",
    "FaultCode",
]


class State(IntEnum, shape=1):
    RUNNING = 0
    FAULTED = 1


class FaultCode(IntEnum):
    UNSET = 0
    ILLEGAL_INSTRUCTION = 1
    PC_MISALIGNED = 2


class LsSize(IntEnum, shape=2):
    B = 0
    H = 1
    W = 2


class Top(Elaboratable):
    ILEN = 32
    XLEN = 32

    sysmem: Memory
    reg_inits: Optional[dict[str, int]]
    track_reg_written: bool

    sysmem_rd: ReadPort
    sysmem_wr: WritePort

    state: Signal
    fault_code: Signal
    fault_insn: Signal

    xreg: Array[Signal]
    xreg_written: Optional[Array[Signal]]
    pc: Signal
    partial_read: Signal

    ls_reg: Signal
    ls_size: Signal

    def __init__(self, *, sysmem=None, reg_inits=None, track_reg_written=False):
        self.sysmem = sysmem or Memory(
            width=16,
            depth=1024 // 2,
        )
        self.reg_inits = reg_inits
        self.track_reg_written = track_reg_written

        self.state = Signal(State)
        self.fault_code = Signal(FaultCode)
        self.fault_insn = Signal(self.ILEN)

        self.xreg = Array(
            Signal(self.XLEN, reset=self.reg_reset(xn)) for xn in range(32)
        )
        if self.track_reg_written:
            self.xreg_written = Array(Signal() for _ in range(32))

        self.pc = Signal(self.XLEN)
        self.partial_read = Signal(16)

        self.ls_reg = Signal(range(32))
        self.ls_size = Signal(LsSize)

    def reg_reset(self, xn):
        if xn == 0:
            return 0
        v = (self.reg_inits or {}).get(f"x{xn}", 0)
        if v < 0:
            v += 2**self.XLEN
        return v

    def elaborate(self, platform):
        m = Module()

        self.sysmem_rd = m.submodules.sysmem_rd = self.sysmem.read_port()
        self.sysmem_wr = m.submodules.sysmem_wr = self.sysmem.write_port()

        m.d.comb += self.state.eq(State.RUNNING)

        with m.FSM():
            # Blowing everything ridiculously apart before we start getting a
            # pipeline going.
            with m.State("fetch.init0"):
                m.d.sync += [
                    self.sysmem_rd.addr.eq(self.pc >> 1),
                    self.sysmem_wr.en.eq(0),
                ]
                m.next = "fetch.init1"

                with m.If(self.pc[:2].any()):
                    m.d.sync += self.fault(FaultCode.PC_MISALIGNED)
                    m.next = "faulted"

            with m.State("fetch.init1"):
                m.d.sync += self.sysmem_rd.addr.eq((self.pc >> 1) | 0b1)
                m.next = "fetch.read0"

            with m.State("fetch.read0"):
                m.d.sync += self.partial_read.eq(self.sysmem_rd.data)
                m.next = "fetch.resolve"

            with m.State("fetch.resolve"):
                insn = Cat(self.partial_read, self.sysmem_rd.data)
                assert len(insn) == self.ILEN
                with m.If(
                    (insn[:16] == 0)
                    | (insn[: self.ILEN] == C(1, 1).replicate(self.ILEN))
                ):
                    m.d.sync += self.fault(FaultCode.ILLEGAL_INSTRUCTION, insn)
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
                    m.next = "fetch.init0"
                    m.d.sync += self.pc.eq(self.pc + 4)

                    with m.Switch(v_i.opcode):
                        with m.Case(Opcode.LOAD):
                            with m.Switch(v_i.funct3):
                                with m.Case(OpLoadFunct.LW):
                                    # Forcibly 16-bit aligned without a raise.
                                    # Whoops XXX.
                                    m.d.sync += [
                                        self.pc.eq(self.pc),
                                        self.sysmem_rd.addr.eq(
                                            (self.xreg[v_i.rs1] + v_i.imm.as_signed())
                                            >> 1
                                        ),
                                        self.ls_reg.eq(v_i.rd),
                                        self.ls_size.eq(4),
                                    ]
                                    m.next = "lw.init1"
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
                                    )
                                    m.next = "faulted"
                        with m.Case(Opcode.MISC_MEM):
                            with m.Switch(v_i.funct3):
                                with m.Case(OpMiscMemFunct.FENCE):
                                    pass  # XXX no-op
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
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
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
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
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
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
                            with m.Switch(v_s.funct3):
                                with m.Case(OpStoreFunct.SW):
                                    # Forcibly 16-bit aligned without a raise.
                                    # Sorry. XXX
                                    m.d.sync += [
                                        self.pc.eq(self.pc),
                                        self.sysmem_wr.addr.eq(
                                            (self.xreg[v_s.rs1] + imm.as_signed()) >> 1
                                        ),
                                        self.sysmem_wr.data.eq(self.xreg[v_s.rs2][:16]),
                                        self.sysmem_wr.en.eq(1),
                                        self.ls_reg.eq(v_s.rs2),
                                    ]
                                    m.next = "sw.write1"
                                with m.Default():
                                    m.d.sync += self.fault(
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
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
                                        FaultCode.ILLEGAL_INSTRUCTION, insn
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
                        with m.Default():
                            m.d.sync += self.fault(FaultCode.ILLEGAL_INSTRUCTION, insn)
                            m.next = "faulted"

            with m.State("lw.init1"):
                m.d.sync += self.sysmem_rd.addr.eq(self.sysmem_rd.addr + 1)
                m.next = "lw.read0"

            with m.State("lw.read0"):
                m.d.sync += self.partial_read.eq(self.sysmem_rd.data)
                m.next = "lw.resolve"

            with m.State("lw.resolve"):
                # TODO: honour ls_size
                # TODO: l[hb]u?
                data = Cat(self.partial_read, self.sysmem_rd.data)
                m.d.sync += [
                    self.pc.eq(self.pc + 4),
                    self.write_xreg(self.ls_reg, data),
                ]
                m.next = "fetch.init0"

            with m.State("sw.write1"):
                # TODO: honour ls_size
                # TODO: s[hb]
                m.d.sync += [
                    self.pc.eq(self.pc + 4),
                    self.sysmem_wr.addr.eq(self.sysmem_wr.addr + 1),
                    self.sysmem_wr.data.eq(self.xreg[self.ls_reg][16:]),
                    self.sysmem_wr.en.eq(1),
                ]
                m.next = "fetch.init0"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        m.d.sync += self.xreg[0].eq(0)

        return m

    def write_xreg(self, xn, value):
        assigns = [self.xreg[xn].eq(value)]
        if self.track_reg_written:
            assigns.append(self.xreg_written[xn].eq(1))
        return assigns

    def fault(self, code, insn=None):
        assigns = [self.fault_code.eq(code)]
        if insn is not None:
            assigns.append(self.fault_insn.eq(insn))
        return assigns
