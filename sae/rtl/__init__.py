from typing import Optional

from amaranth import Array, C, Elaboratable, Module, Mux, Signal, signed
from amaranth.hdl import Memory, ReadPort, WritePort
from amaranth.lib.enum import IntEnum

from . import rv32
from .rv32 import InsI, InsR, InsU, Opcode, OpImmFunct, OpRegFunct, Reg

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
                rv32.Addi(Reg.X1, Reg.X0, 3),
                rv32.Addi(Reg.X2, Reg.X1, 5),
                rv32.Srai(Reg.X3, Reg.X2, 3),
                0,
            ],
        )
        self.reg_inits = reg_inits
        self.track_reg_written = track_reg_written

        self.state = Signal(State)
        self.xreg = Array(
            Signal(self.XLEN, reset=self.reg_reset(xn)) for xn in range(32)
        )
        if self.track_reg_written:
            self.xreg_written = Array(Signal() for _ in range(32))

        self.pc = Signal(self.XLEN)

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
                    v_r = InsR(self.sysmem_rd.data)

                    # sx I imm to XLEN
                    v_sxi = Signal(signed(32))
                    m.d.comb += v_sxi.eq(v_i.imm.as_signed())

                    with m.Switch(v_i.opcode):
                        with m.Case(Opcode.OP_IMM):
                            with m.Switch(v_i.funct):
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
                        with m.Case(Opcode.LUI):
                            m.d.sync += self.write_xreg(v_u.rd, v_u.imm << 12)
                        with m.Case(Opcode.AUIPC):
                            m.d.sync += self.write_xreg(
                                v_u.rd, (v_u.imm << 12) + self.pc
                            )
                    m.d.sync += self.pc.eq(self.pc + 4)
                    m.next = "fetch.init"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        m.d.sync += self.xreg[0].eq(0)

        return m

    def write_xreg(self, xn, value):
        assigns = [self.xreg[xn].eq(value)]
        if self.track_reg_written:
            assigns += [self.xreg_written[xn].eq(1)]
        return assigns
