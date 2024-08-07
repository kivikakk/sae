from typing import Optional

from amaranth import C, Cat, Module, Mux, Shape, Signal
from amaranth.lib import data, memory, stream
from amaranth.lib.enum import Enum
from amaranth.lib.wiring import Component, In, Out, Signature, connect
from amaranth.utils import ceil_log2

__all__ = ["AccessWidth", "MMU", "MMUReadBusSignature", "MMUWriteBusSignature", "Peripheral"]


class AccessWidth(Enum, shape=2):
    BYTE = 0
    HALF = 1
    WORD = 2


class MMUReadBusSignature(Signature):
    class Request(data.StructLayout):
        def __init__(self, addr_width):
            super().__init__({
                "addr": addr_width,
                "width": AccessWidth,
            })

    def __init__(self, addr_width, data_width):
        super().__init__({
            "req": In(stream.Signature(self.Request(addr_width))),
            "resp": Out(stream.Signature(data_width)),
        })


class MMUWriteBusSignature(Signature):
    class Request(data.StructLayout):
        def __init__(self, addr_width, data_width):
            super().__init__({
                "addr": addr_width,
                "width": AccessWidth,
                "data": data_width,
            })

    def __init__(self, addr_width, data_width):
        super().__init__({
            "req": In(stream.Signature(self.Request(addr_width, data_width))),
        })


class MMU(Component):
    read: In(MMUReadBusSignature(32, 32))
    write: In(MMUWriteBusSignature(32, 32))
    mmu_read: "MMURead"
    mmu_write: "MMUWrite"
    sysmem: memory.Memory
    peripherals: dict[int, object]

    def __init__(self, *, sysmem, peripherals={}):
        super().__init__()
        assert Shape.cast(sysmem.shape).width == 16
        self.sysmem = sysmem
        self.peripherals = peripherals

    def elaborate(self, platform):
        m = Module()

        m.submodules.sysmem = sysmem = self.sysmem
        rp = sysmem.read_port()
        wp = sysmem.write_port(granularity=8)

        self.mmu_read = m.submodules.mmu_read = mmu_read = MMURead(sysmem=sysmem)
        connect(m, rp, mmu_read.port)
        with m.If(~self.read.req.payload.addr[31]):
            connect(m, self.read, mmu_read.read)

        self.mmu_write = m.submodules.mmu_write = mmu_write = MMUWrite(sysmem=sysmem)
        connect(m, wp, mmu_write.port)
        with m.If(~self.write.req.payload.addr[31]):
            connect(m, self.write, mmu_write.write)

        # TODO: if we want to support SPRAM on main memory. Note that we can't
        # init it, so there needs to be some other way of doing that. (Note also
        # that Amaranth doesn't support this yet, since we always generate a
        # $meminit_v2.)
        #
        # m.d.comb += rp.en.eq(~wp.en.any())

        # XXX: the below is all pretty much not there for initiating
        # ready/valid, is it?
        for cid, p in self.peripherals.items():
            pc = p.connection(cid)
            m.submodules += pc

            with m.If(self.read.req.payload.addr[31] & (self.read.req.payload.addr[:16] == pc.cid)):
                connect(m, self.read, pc.read)
            with m.If(self.write.req.payload.addr[31] & (self.write.req.payload.addr[:16] == pc.cid)):
                connect(m, self.write, pc.write)

        return m


class MMURead(Component):
    def __init__(self, *, sysmem):
        super().__init__({
            "read": Out(MMUReadBusSignature(32, 32)),
            "port": In(memory.ReadPort.Signature(
                addr_width=ceil_log2(sysmem.depth), shape=sysmem.shape
            )),
        })

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
        m.d.comb += self.read.req.ready.eq(0)
        m.d.comb += self.read.resp.valid.eq(valid & ~self.read.req.valid)

        req_addr = Signal.like(self.read.req.payload.addr)
        req_width = Signal.like(self.read.req.payload.width)

        with m.FSM():
            with m.State("init"):
                m.d.comb += self.read.req.ready.eq(1)

                with m.If(self.read.req.valid):
                    m.d.sync += [
                        valid.eq(0),
                        self.port.addr.eq(self.read.req.payload.addr >> 1),

                        req_addr.eq(self.read.req.payload.addr),
                        req_width.eq(self.read.req.payload.width),
                    ]
                    m.next = "pipe"

            with m.State("pipe"):
                m.d.sync += self.port.addr.eq(self.port.addr + 1)

                with m.If(
                    (req_width == AccessWidth.WORD)
                    | ((req_width == AccessWidth.HALF) & req_addr[0])
                ):
                    m.next = "coll0"
                with m.Else():
                    m.next = "coll"

            with m.State("coll"):
                # aligned half, or byte
                m.d.sync += [
                    self.read.resp.payload.eq(Mux(
                        req_width == AccessWidth.HALF,
                        self.port.data,
                        self.port.data.word_select(req_addr[0], 8),
                    )),
                    valid.eq(1),
                ]
                m.next = "init"

            with m.State("coll0"):
                # word, or unaligned half
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.read.resp.payload.eq(self.port.data),
                ]
                m.next = "coll1"

            with m.State("coll1"):
                with m.If(req_width == AccessWidth.HALF):
                    # unaligned half
                    m.d.sync += [
                        self.read.resp.payload.eq(self.read.resp.payload[8:] | (self.port.data[:8] << 8)),
                        valid.eq(1),
                    ]
                    m.next = "init"
                with m.Elif(~req_addr[0]):
                    # aligned word
                    m.d.sync += [
                        self.read.resp.payload.eq(self.read.resp.payload | (self.port.data << 16)),
                        valid.eq(1),
                    ]
                    m.next = "init"
                with m.Else():
                    # unaligned word
                    m.d.sync += self.read.resp.payload.eq(self.read.resp.payload[8:] | (self.port.data << 8))
                    m.next = "coll2"

            with m.State("coll2"):
                m.d.sync += [
                    self.read.resp.payload.eq(self.read.resp.payload | (self.port.data[:8] << 24)),
                    valid.eq(1),
                ]
                m.next = "init"

        return m


class MMUWrite(Component):
    def __init__(self, *, sysmem):
        super().__init__({
            "write": Out(MMUWriteBusSignature(32, 32)),
            "port": In(memory.WritePort.Signature(
                addr_width=ceil_log2(sysmem.depth),
                shape=sysmem.shape,
                granularity=8,
            )),
        })

    def elaborate(self, platform):
        m = Module()

        m.d.sync += self.write.req.ready.eq(1)

        req_payload = Signal.like(self.write.req.payload.data)

        with m.FSM():
            with m.State("init"):
                m.d.sync += self.port.en.eq(0)

                with m.If(self.write.req.valid):
                    with m.Switch(self.write.req.payload.width):
                        with m.Case(AccessWidth.BYTE):
                            m.d.sync += [
                                self.port.addr.eq(self.write.req.payload.addr >> 1),
                                self.port.data.eq(self.write.req.payload.data[:8].replicate(2)),
                                self.port.en.eq(Mux(self.write.req.payload.addr[0], 0b10, 0b01)),
                            ]

                        with m.Case(AccessWidth.HALF):
                            m.d.sync += self.port.addr.eq(self.write.req.payload.addr >> 1)
                            with m.If(~self.write.req.payload.addr[0]):
                                m.d.sync += [
                                    self.port.data.eq(self.write.req.payload.data[:16]),
                                    self.port.en.eq(0b11),
                                ]
                            with m.Else():
                                # unaligned
                                m.d.sync += [
                                    self.write.req.ready.eq(0),
                                    self.port.data.eq(
                                        Cat(self.write.req.payload.data[8:16], self.write.req.payload.data[:8])
                                    ),
                                    self.port.en.eq(0b10),
                                    req_payload.eq(self.write.req.payload.data),
                                ]
                                m.next = "half.unaligned"

                        with m.Case(AccessWidth.WORD):
                            m.d.sync += [
                                self.write.req.ready.eq(0),
                                self.port.addr.eq(self.write.req.payload.addr >> 1),
                                req_payload.eq(self.write.req.payload.data),
                            ]
                            with m.If(~self.write.req.payload.addr[0]):
                                m.d.sync += [
                                    self.port.data.eq(self.write.req.payload.data[:16]),
                                    self.port.en.eq(0b11),
                                ]
                                m.next = "word"
                            with m.Else():
                                m.d.sync += [
                                    self.port.data.eq(Cat(C(0, 8), self.write.req.payload.data[:8])),
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
                    self.port.data.eq(req_payload[16:]),
                    self.port.en.eq(0b11),
                ]
                m.next = "init"

            with m.State("word.unaligned"):
                m.d.sync += [
                    self.write.req.ready.eq(0),
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.data.eq(req_payload[8:24]),
                    self.port.en.eq(0b11),
                ]
                m.next = "word.unaligned.fish"

            with m.State("word.unaligned.fish"):
                m.d.sync += [
                    self.port.addr.eq(self.port.addr + 1),
                    self.port.data.eq(req_payload[24:]),
                    self.port.en.eq(0b01),
                ]
                m.next = "init"

        return m
