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

    def elaborate(self, platform):
        m = Module()

        m.submodules.sysmem = self.sysmem
        sysmem_rd = self.sysmem.read_port()

        r_addr = Signal(32, init=-1)
        r_width = Signal(AccessWidth)

        underlying_valid = Signal()
        m.d.comb += self.valid.eq(
            (r_addr == self.addr) & (r_width == self.width) & underlying_valid
        )

        #  0 . 1 | 2 . 3 | 4 . 5 | 6    acc#
        # ^^^^^^^|^^^^^^^|^^^^^^^|^^^^^^^^^^
        #  [-----|-----] |       |       2
        #      [-|-------|-]     |       3
        #        | [-----|-----] |       2
        #        |     [-|-------|-]     3
        #  [---] |       |       |       1
        #      [-|-]     |       |       2
        #  []    |       |       |       1
        #     [] |       |       |       1
        #
        # Note that:
        #   * word accesses take 2+a[0] reads,
        #   * half accesses take 1+a[0] reads, and
        #   * byte accesses take 1 read.

        with m.FSM():
            with m.State("init"):
                with m.If((self.addr != r_addr) | (self.width != r_width)):
                    m.d.sync += [
                        r_addr.eq(self.addr),
                        r_width.eq(self.width),
                        underlying_valid.eq(0),
                        sysmem_rd.addr.eq(self.addr >> 1),
                    ]
                    m.next = "pipe"

            with m.State("pipe"):
                m.d.sync += sysmem_rd.addr.eq(sysmem_rd.addr + 1)

                with m.If(
                    (r_width == AccessWidth.WORD)
                    | ((r_width == AccessWidth.HALF) & r_addr[0])
                ):
                    m.next = "coll0"
                with m.Else():
                    m.next = "coll"

            with m.State("coll"):
                # aligned half, or byte
                m.d.sync += [
                    self.value.eq(
                        Mux(
                            r_width == AccessWidth.HALF,
                            sysmem_rd.data,
                            sysmem_rd.data.word_select(r_addr[0], 8),
                        )
                    ),
                    underlying_valid.eq(1),
                ]
                m.next = "init"

            with m.State("coll0"):
                # word, or unaligned half
                m.d.sync += [
                    sysmem_rd.addr.eq(sysmem_rd.addr + 1),
                    self.value.eq(sysmem_rd.data),
                ]
                m.next = "coll1"

            with m.State("coll1"):
                with m.If(r_width == AccessWidth.HALF):
                    # unaligned half
                    m.d.sync += [
                        self.value.eq(self.value[8:] | (sysmem_rd.data[:8] << 8)),
                        underlying_valid.eq(1),
                    ]
                    m.next = "init"
                with m.Elif(~r_addr[0]):
                    # aligned word
                    m.d.sync += [
                        self.value.eq(self.value | (sysmem_rd.data << 16)),
                        underlying_valid.eq(1),
                    ]
                    m.next = "init"
                with m.Else():
                    # unaligned word
                    m.d.sync += self.value.eq(self.value[:8] | (sysmem_rd.data << 8))
                    m.next = "coll2"

            with m.State("coll2"):
                m.d.sync += [
                    self.value.eq(self.value | (sysmem_rd.data[:8] << 24)),
                    underlying_valid.eq(1),
                ]
                m.next = "init"

        return m
