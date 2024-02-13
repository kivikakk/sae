from amaranth import Elaboratable, Module, Signal, Array, C, signed
from amaranth.hdl.mem import Memory, ReadPort, WritePort
from amaranth.lib.enum import IntEnum

from .rv32 import Opcode, OpImmFunct, Reg, InsI, InsIS


__all__ = ["Top", "State"]


class State(IntEnum):
    RUNNING = 0
    FAULTED = 1


class Top(Elaboratable):
    ILEN = 32
    XLEN = 32

    sysmem_rd: ReadPort
    sysmem_wr: WritePort

    state: Signal
    xreg: Array[Signal]
    pc: Signal

    def __init__(self, *, sysmem=None):
        self.sysmem = sysmem or Memory(
            width=8 * 4,
            depth=1024 // 4,
            init=[
                # ADDI x1, x0, 3 (= MV x1, 3)
                InsI(Opcode.OP_IMM, OpImmFunct.ADDI, Reg.X0, Reg.X1, C(3, 12)),
                # ADDI x2, x1, 5
                InsI(Opcode.OP_IMM, OpImmFunct.ADDI, Reg.X1, Reg.X2, C(5, 12)),
                # !
                0,
            ],
        )

    def elaborate(self, platform):
        m = Module()

        self.sysmem_rd = m.submodules.sysmem_rd = self.sysmem.read_port()
        self.sysmem_wr = m.submodules.sysmem_wr = self.sysmem.write_port()

        self.state = Signal(State)
        self.xreg = Array(Signal(self.XLEN) for _ in range(32))
        self.pc = Signal(self.XLEN)

        m.d.comb += self.state.eq(State.RUNNING)

        with m.FSM():
            # Blowing everything ridiculously apart before we start getting a
            # pipeline going.
            with m.State("fetch.init"):
                m.d.sync += self.sysmem_rd.addr.eq(self.pc)
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
                    # we can only add for now, so let's add.
                    v = InsIS(self.sysmem_rd.data)

                    # sx imm to XLEN
                    sxi = Signal(signed(32))
                    m.d.comb += sxi.eq(v.imm.as_signed())

                    with m.Switch(v.funct):
                        with m.Case(OpImmFunct.ADDI):
                            m.d.sync += self.xreg[v.rd].eq(self.xreg[v.rs1] + sxi)
                        with m.Case(OpImmFunct.SLTI):
                            m.d.sync += self.xreg[v.rd].eq(self.xreg[v.rs1] < sxi)
                        with m.Case(OpImmFunct.SLTIU):
                            m.d.sync += self.xreg[v.rd].eq(
                                self.xreg[v.rs1] < sxi.as_unsigned()
                            )

                    m.d.sync += self.pc.eq(self.pc + 1)
                    m.next = "fetch.init"

            with m.State("faulted"):
                m.d.comb += self.state.eq(State.FAULTED)

        m.d.sync += self.xreg[0].eq(0)

        return m
