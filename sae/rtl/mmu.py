from amaranth import Module, Mux, Shape, Signal
from amaranth.lib.enum import IntEnum
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import Component, In, Out, Signature, connect, flipped

__all__ = ["MMU", "AccessWidth"]


class AccessWidth(IntEnum, shape=2):  # type: ignore
    BYTE = 0
    HALF = 1
    WORD = 2


class MMUReaderSignature(Signature):
    def __init__(self, width):
        super().__init__(
            {
                "addr": Out(width),
                "width": Out(AccessWidth),
                "value": In(width),
                "valid": In(1),
            }
        )


class MMU(Component):
    read: In(MMUReaderSignature(32))
    data: In(32)
    rdy: Out(1)  # write rdy
    ack: In(1)  # write strobe

    sysmem: Memory

    def __init__(self, sysmem):
        super().__init__()
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem

    def elaborate(self, platform):
        m = Module()

        mmuread = m.submodules.mmuread = MMURead(self.sysmem)
        connect(m, flipped(self.read), mmuread)

        return m


class MMURead(Component):
    def __init__(self, sysmem):
        super().__init__(MMUReaderSignature(32).flip())
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem
        self.state = Signal(range(6))

    def elaborate(self, platform):
        m = Module()

        m.submodules.sysmem = self.sysmem
        sysmem_rd = self.sysmem.read_port()

        r_addr = Signal(32, init=-1)
        r_width = Signal(AccessWidth)

        state = self.state

        underlying_valid = Signal()
        m.d.comb += self.valid.eq(
            (r_addr == self.addr) & (r_width == self.width) & underlying_valid
        )

        with m.FSM():
            with m.State("init"):
                m.d.comb += state.eq(1)

                # XXX: for now we ignore un-32-bit-aligned requests entirely lol
                with m.If(
                    ((self.addr != r_addr) | (self.width != r_width))
                    & ~self.addr[:2].any()
                ):
                    m.d.sync += [
                        r_addr.eq(self.addr),
                        r_width.eq(self.width),
                        underlying_valid.eq(0),
                        sysmem_rd.addr.eq(self.addr >> 1),
                    ]
                    m.next = "pipe0"

            with m.State("pipe0"):
                m.d.comb += state.eq(2)

                with m.If(r_width == AccessWidth.WORD):
                    m.d.sync += sysmem_rd.addr.eq(sysmem_rd.addr + 1)
                    m.next = "coll0"
                with m.Else():
                    m.next = "coll"

            with m.State("coll"):
                m.d.comb += state.eq(3)

                m.d.sync += [
                    self.value.eq(
                        Mux(
                            r_width == AccessWidth.HALF,
                            sysmem_rd.data,
                            sysmem_rd.data[:8],
                        )
                    ),
                    underlying_valid.eq(1),
                ]
                m.next = "init"

            with m.State("coll0"):
                m.d.comb += state.eq(4)

                m.d.sync += self.value.eq(sysmem_rd.data)
                m.next = "coll1"

            with m.State("coll1"):
                m.d.comb += state.eq(5)

                m.d.sync += [
                    self.value.eq(self.value | (sysmem_rd.data << 16)),
                    underlying_valid.eq(1),
                ]
                m.next = "init"

        return m
