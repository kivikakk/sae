from typing import Optional

from amaranth import C, Cat, Module, Mux, Shape, Signal
from amaranth.lib import memory
from amaranth.lib.enum import IntEnum
from amaranth.lib.wiring import Component, In, Out, Signature, connect
from amaranth.utils import ceil_log2

from .uart import UART

__all__ = ["MMU", "AccessWidth"]


class AccessWidth(IntEnum, shape=2):
    BYTE = 0
    HALF = 1
    WORD = 2


class MMUReadBusSignature(Signature):
    def __init__(self, addr_width, data_width):
        super().__init__({
            "addr": In(addr_width),
            "width": In(AccessWidth),
            "ack": In(1),
            "rdy": Out(1),
            "value": Out(data_width),
            "valid": Out(1),
        })


class MMUWriteBusSignature(Signature):
    def __init__(self, addr_width, data_width):
        super().__init__({
            "addr": In(addr_width),
            "width": In(AccessWidth),
            "data": In(data_width),
            "ack": In(1),
            "rdy": Out(1),
        })


class MMU(Component):
    UART_OFFSET = 0x0001_0000

    read: In(MMUReadBusSignature(32, 32))
    write: In(MMUWriteBusSignature(32, 32))
    mmu_read: "MMURead"
    mmu_write: "MMUWrite"
    sysmem: memory.Memory
    uart: Optional[UART]

    def __init__(self, *, sysmem, uart=None):
        super().__init__()
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem
        self.uart = uart

    def elaborate(self, platform):
        m = Module()

        m.submodules.sysmem = sysmem = self.sysmem
        self.mmu_read = m.submodules.mmu_read = mmu_read = MMURead(sysmem=sysmem, uart=self.uart)
        connect(m, self.read, mmu_read.read)
        connect(m, sysmem.read_port(), mmu_read.port)

        self.mmu_write = m.submodules.mmu_write = mmu_write = MMUWrite(sysmem=sysmem, uart=self.uart)
        connect(m, self.write, mmu_write.write)
        connect(m, sysmem.write_port(granularity=8), mmu_write.port)

        return m


class MMURead(Component):
    uart: Optional[UART]

    def __init__(self, *, sysmem, uart=None):
        super().__init__({
            "read": Out(MMUReadBusSignature(32, 32)),
            "port": In(memory.ReadPort.Signature(
                addr_width=ceil_log2(sysmem.depth), shape=sysmem.shape
            )),
        })
        self.uart = uart

    def elaborate(self, platform):
        m = Module()

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

        valid = Signal()
        m.d.comb += self.read.rdy.eq(0)
        m.d.comb += self.read.valid.eq(valid & ~self.read.ack)

        with m.FSM():
            with m.State("init"):
                m.d.comb += self.read.rdy.eq(1)

                with m.If(self.read.ack):
                    m.d.sync += [
                        valid.eq(0),
                        self.port.addr.eq(self.read.addr >> 1),
                    ]
                    m.next = "pipe"

                    if self.uart:
                        with m.If(
                            (self.read.width == AccessWidth.BYTE)
                            & (self.read.addr == MMU.UART_OFFSET)
                        ):
                            with m.If(self.uart.rd.valid):
                                m.d.sync += [
                                    self.uart.rd.ready.eq(1),
                                    self.read.value.eq(self.uart.rd.payload),
                                    valid.eq(1),
                                ]
                                m.next = "uart.dessert"
                            with m.Else():
                                m.d.sync += [
                                    self.read.value.eq(0),
                                    valid.eq(1),  # ideally we actually identify there's nothing to read!
                                ]
                                m.next = "uart.dessert"  # XXX probably unnecessary

            if self.uart:
                with m.State("uart.dessert"):
                    # may not need this state at all.
                    m.d.sync += self.uart.rd.ready.eq(0)
                    m.next = "init"

            with m.State("pipe"):
                m.d.sync += self.port.addr.eq(self.port.addr + 1)

                with m.If(
                    (self.read.width == AccessWidth.WORD)
                    | ((self.read.width == AccessWidth.HALF) & self.read.addr[0])
                ):
                    m.next = "coll0"
                with m.Else():
                    m.next = "coll"

            with m.State("coll"):
                # aligned half, or byte
                m.d.sync += [
                    self.read.value.eq(
                        Mux(
                            self.read.width == AccessWidth.HALF,
                            self.port.data,
                            self.port.data.word_select(self.read.addr[0], 8),
                        )
                    ),
                    valid.eq(1),
                ]
                m.next = "init"

            with m.State("coll0"):
                # word, or unaligned half
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.read.value.eq(self.port.data),
                ]
                m.next = "coll1"

            with m.State("coll1"):
                with m.If(self.read.width == AccessWidth.HALF):
                    # unaligned half
                    m.d.sync += [
                        self.read.value.eq(self.read.value[8:] | (self.port.data[:8] << 8)),
                        valid.eq(1),
                    ]
                    m.next = "init"
                with m.Elif(~self.read.addr[0]):
                    # aligned word
                    m.d.sync += [
                        self.read.value.eq(self.read.value | (self.port.data << 16)),
                        valid.eq(1),
                    ]
                    m.next = "init"
                with m.Else():
                    # unaligned word
                    m.d.sync += self.read.value.eq(self.read.value[8:] | (self.port.data << 8))
                    m.next = "coll2"

            with m.State("coll2"):
                m.d.sync += [
                    self.read.value.eq(self.read.value | (self.port.data[:8] << 24)),
                    valid.eq(1),
                ]
                m.next = "init"

        return m


class MMUWrite(Component):
    uart: Optional[UART]

    def __init__(self, *, sysmem, uart=None):
        super().__init__(
            {
                "write": Out(MMUWriteBusSignature(32, 32)),
                "port": In(memory.WritePort.Signature(
                    addr_width=ceil_log2(sysmem.depth),
                    shape=sysmem.shape,
                    granularity=8,
                )),
            }
        )
        self.uart = uart

    def elaborate(self, platform):
        m = Module()

        m.d.sync += self.write.rdy.eq(1)
        if self.uart:
            m.d.sync += self.uart.wr.valid.eq(0)

        with m.FSM():
            with m.State("init"):
                m.d.sync += self.port.en.eq(0)

                with m.If(self.write.ack):
                    with m.Switch(self.write.width):
                        with m.Case(AccessWidth.BYTE):
                            m.d.sync += [
                                self.port.addr.eq(self.write.addr >> 1),
                                self.port.data.eq(self.write.data[:8].replicate(2)),
                                self.port.en.eq(Mux(self.write.addr[0], 0b10, 0b01)),
                            ]
                            if self.uart:
                                with m.If(self.write.addr == MMU.UART_OFFSET):
                                    m.d.sync += [
                                        self.uart.wr.payload.eq(self.write.data[:8]),
                                        self.uart.wr.valid.eq(1),
                                        self.port.en.eq(0),
                                    ]

                        with m.Case(AccessWidth.HALF):
                            m.d.sync += self.port.addr.eq(self.write.addr >> 1)
                            with m.If(~self.write.addr[0]):
                                m.d.sync += [
                                    self.port.data.eq(self.write.data[:16]),
                                    self.port.en.eq(0b11),
                                ]
                            with m.Else():
                                # unaligned
                                m.d.sync += [
                                    self.write.rdy.eq(0),
                                    self.port.data.eq(
                                        Cat(self.write.data[8:16], self.write.data[:8])
                                    ),
                                    self.port.en.eq(0b10),
                                ]
                                m.next = "half.unaligned"

                        with m.Case(AccessWidth.WORD):
                            m.d.sync += [
                                self.write.rdy.eq(0),
                                self.port.addr.eq(self.write.addr >> 1),
                            ]
                            with m.If(~self.write.addr[0]):
                                m.d.sync += [
                                    self.port.data.eq(self.write.data[:16]),
                                    self.port.en.eq(0b11),
                                ]
                                m.next = "word"
                            with m.Else():
                                m.d.sync += [
                                    self.port.data.eq(Cat(C(0, 8), self.write.data[:8])),
                                    self.port.en.eq(0b10),
                                ]
                                m.next = "word.unaligned"

            with m.State("half.unaligned"):
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.en.eq(0b01),
                ]
                m.next = "init"

            with m.State("word"):
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.data.eq(self.write.data[16:]),
                    self.port.en.eq(0b11),
                ]
                m.next = "init"

            with m.State("word.unaligned"):
                m.d.sync += [
                    self.write.rdy.eq(0),
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.data.eq(self.write.data[8:24]),
                    self.port.en.eq(0b11),
                ]
                m.next = "word.unaligned.fish"

            with m.State("word.unaligned.fish"):
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.data.eq(self.write.data[24:]),
                    self.port.en.eq(0b01),
                ]
                m.next = "init"

        return m
