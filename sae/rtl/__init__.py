from typing import Optional

from amaranth import Array, C, Elaboratable, Module, Mux, Signal, signed
from amaranth.hdl.mem import Memory, ReadPort, WritePort
from amaranth.lib.enum import IntEnum

from . import rv32
from .rv32 import InsI, InsU, Opcode, OpImmFunct, Reg

__all__ = [
    "Top",
    "State",
]


class State(IntEnum):
    RUNNING = 0
    FAULTED = 1


class Top(Elaboratable):
    ILEN = 32
    XLEN = 32

    sysmem: Memory
    reg_inits: Optional[dict[str, int]]
    track_reg_written: bool

    sysmem_rd: ReadPort
    sysmem_wr: WritePort

    state: Signal
    xreg: Array[Signal]
    xreg_written: Optional[Array[Signal]]
    pc: Signal

    def __init__(self, *, sysmem=None, reg_inits=None, track_reg_written=False):
        self.sysmem = sysmem or Memory(
            width=8 * 4,
            depth=1024 // 4,
            init=[
                rv32.Addi(Reg.X0, Reg.X1, 3),
                rv32.Addi(Reg.X1, Reg.X2, 5),
                rv32.Srai(Reg.X2, Reg.X3, 3),
                0,
            ],
        )
        self.reg_inits = reg_inits
        self.track_reg_written = track_reg_written

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

        self.state = Signal(State)
        self.xreg = Array(
            Signal(self.XLEN, reset=self.reg_reset(xn)) for xn in range(32)
        )
        if self.track_reg_written:
            self.xreg_written = Array(Signal() for _ in range(32))

        self.pc = Signal(self.XLEN)

        m.d.comb += self.state.eq(State.RUNNING)

        with m.FSM():
            # Blowing everything ridiculously apart before we start getting a
            # pipeline going.
            with m.State("fetch.init"):
                m.d.sync += self.sysmem_rd.addr.eq(self.pc >> 2)
                m.next = "fetch.delay"

            with m.State("fetch.delay"):
                m.next = "fetch.resolve"

            with m.State("fetch.resolve"):
                with m.If(
                    (self.sysmem_rd.data[:16] == 0)
                    | (self.sysmem_rd.data[: self.ILEN] == C(1, 1).replicate(self.ILEN))
                ):
                    m.next = "faulted"
                with m.Else():
                    v_i = InsI(self.sysmem_rd.data)
                    v_u = InsU(self.sysmem_rd.data)

                    # sx I imm to XLEN
                    v_sxi = Signal(signed(32))
                    m.d.comb += v_sxi.eq(v_i.imm.as_signed())

                    with m.Switch(v_i.opcode):
                        with m.Case(Opcode.OP_IMM):
                            with m.Switch(v_i.funct):
                                with m.Case(OpImmFunct.ADDI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] + v_sxi
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.SLTI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] < v_sxi
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.SLTIU):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] < v_sxi.as_unsigned()
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.ANDI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] & v_sxi
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.ORI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] | v_sxi
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.XORI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] ^ v_sxi
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.SLLI):
                                    m.d.sync += self.xreg[v_i.rd].eq(
                                        self.xreg[v_i.rs1] << v_i.imm[:5]
                                    )
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                                with m.Case(OpImmFunct.SRI):
                                    rs1 = self.xreg[v_i.rs1]
                                    rs1 = Mux(v_i.imm[10], rs1.as_signed(), rs1)
                                    m.d.sync += self.xreg[v_i.rd].eq(rs1 >> v_i.imm[:5])
                                    if self.track_reg_written:
                                        m.d.sync += self.xreg_written[v_i.rd].eq(1)
                        with m.Case(Opcode.LUI):
                            m.d.sync += self.xreg[v_u.rd].eq(v_u.imm << 12)
                            if self.track_reg_written:
                                m.d.sync += self.xreg_written[v_u.rd].eq(1)
                        with m.Case(Opcode.AUIPC):
                            m.d.sync += self.xreg[v_u.rd].eq(
                                (v_u.imm << 12) | self.pc[:12]
                            )
                            if self.track_reg_written:
                                m.d.sync += self.xreg_written[v_u.rd].eq(1)
                    m.d.sync += self.pc.eq(self.pc + 4)
                    m.next = "fetch.init"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        m.d.sync += self.xreg[0].eq(0)

        return m
