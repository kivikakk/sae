from amaranth import Module, Mux, Shape, Signal
from amaranth.lib.enum import IntEnum
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import Component, In, Out, Signature, connect, flipped

__all__ = ["MMU", "AccessWidth"]


class AccessWidth(IntEnum, shape=2):  # type: ignore
    BYTE = 0
    HALF = 1
    WORD = 2


class MMUReadSignature(Signature):
    def __init__(self, addr_width, data_width):
        super().__init__(
            {
                "addr": Out(addr_width),
                "width": Out(AccessWidth),
                "value": In(data_width),
                "valid": In(1),
            }
        )


class MMUWriteSignature(Signature):
    def __init__(self, addr_width, data_width):
        super().__init__(
            {
                "addr": Out(addr_width),
                "width": Out(AccessWidth),
                "data": Out(data_width),
                "rdy": In(1),
                "ack": Out(1),
            }
        )


class MMU(Component):
    read: In(MMUReadSignature(32, 32))
    write: In(MMUWriteSignature(32, 32))

    sysmem: Memory

    def __init__(self, sysmem):
        super().__init__()
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem

    def elaborate(self, platform):
        m = Module()

        read = m.submodules.read = MMURead(self.sysmem)
        connect(m, flipped(self.read), read)

        write = m.submodules.write = MMUWrite(self.sysmem)
        connect(m, flipped(self.write), write)

        return m


class MMURead(Component):
    def __init__(self, sysmem):
        super().__init__(MMUReadSignature(32, 32).flip())
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


class MMUWrite(Component):
    def __init__(self, sysmem):
        super().__init__(MMUWriteSignature(32, 32).flip())
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem

    def elaborate(self, platform):
        m = Module()

        m.submodules.sysmem = self.sysmem
        sysmem_wr = self.sysmem.write_port(granularity=8)

        m.d.comb += self.rdy.eq(0)

        with m.FSM():
            with m.State("init"):
                m.d.comb += self.rdy.eq(1)

                with m.If(self.ack):
                    m.d.sync += [
                        sysmem_wr.addr.eq(self.addr >> 1),
                        sysmem_wr.data.eq(self.data),
                        sysmem_wr.en.eq(0b01),
                    ]
                    m.next = "unstb"

            with m.State("unstb"):
                m.d.sync += sysmem_wr.en.eq(0)
                m.next = "init"

        return m
