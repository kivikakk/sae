import unittest
from functools import partial

from amaranth import Elaboratable, Module
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick

from .mmu import AccessWidth, MMURead, MMUWrite


def pmrs(mr):
    print(
        f"MMUR: [{(yield mr.state):0>1x}] addr={(yield mr.addr):0>8x}  width={AccessWidth((yield mr.width))}  "
        f"value={(yield mr.value):0>8x}  valid={(yield mr.valid):b}"
    )


class TestBase:
    def waitFor(self, s, *, change_to, ticks):
        for i in range(ticks):
            self.assertNotEqual(
                change_to, (yield s), f"{s} changed to {change_to} after {i} tick(s)"
            )
            yield Tick()
        self.assertEqual(
            change_to,
            (yield s),
            f"{s} didn't change to {change_to} after {ticks} tick(s)",
        )


class TestMMURead(unittest.TestCase, TestBase):
    def simTestbench(self, bench, init):
        mr = MMURead(Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(mr)
        sim.add_clock(1e-6)
        sim.add_testbench(partial(bench, mr))
        sim.run()

    def assertRead(self, addr, width, value, mem):
        ticks = 3
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        def bench(mr):
            yield mr.addr.eq(addr)
            yield mr.width.eq(width)
            yield from self.waitFor(mr.valid, change_to=1, ticks=ticks)
            self.assertEqual(value, (yield mr.value))

        self.simTestbench(bench, mem)

    def test_simple(self):
        mem = [0x1234, 0xABCD]
        self.assertRead(0x00, AccessWidth.BYTE, 0x34, mem)
        self.assertRead(0x01, AccessWidth.BYTE, 0x12, mem)
        self.assertRead(0x02, AccessWidth.BYTE, 0xCD, mem)
        self.assertRead(0x03, AccessWidth.BYTE, 0xAB, mem)
        self.assertRead(0x00, AccessWidth.HALF, 0x1234, mem)
        self.assertRead(0x01, AccessWidth.HALF, 0xCD12, mem)
        self.assertRead(0x02, AccessWidth.HALF, 0xABCD, mem)
        self.assertRead(0x03, AccessWidth.HALF, 0x34AB, mem)
        self.assertRead(0x00, AccessWidth.WORD, 0xABCD1234, mem)
        self.assertRead(0x01, AccessWidth.WORD, 0x34ABCD12, mem)
        self.assertRead(0x02, AccessWidth.WORD, 0x1234ABCD, mem)
        self.assertRead(0x03, AccessWidth.WORD, 0xCD1234AB, mem)

    def test_rejig(self):
        def bench(mr):
            yield Tick()  # I'm kinda annoyed I need this?  But it doesn't repro otherwise ...
            self.assertEqual(AccessWidth.BYTE, (yield mr.width))
            yield mr.width.eq(AccessWidth.WORD)
            yield from self.waitFor(mr.valid, change_to=1, ticks=6)
            self.assertEqual(
                0xABCD1234,
                (yield mr.value),
                f"wanted 0xABCD1234, got {(yield mr.value):x}",
            )

        self.simTestbench(bench, [0x1234, 0xABCD, 0x5678, 0xEF01])


class TestMMUWrite(unittest.TestCase, TestBase):
    def simTestbench(self, bench, init):
        mw = MMUWrite(Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(mw)
        sim.add_clock(1e-6)
        sim.add_testbench(partial(bench, mw))
        sim.run()

    def test_simple(self):
        def bench(mw):
            yield mw.width.eq(AccessWidth.BYTE)
            yield mw.addr.eq(0)
            yield mw.data.eq(0xAAAAAAAA)
            self.waitFor(mw.rdy, change_to=1, ticks=1)
            yield mw.ack.eq(1)
            yield Tick()
            self.assertTrue((yield mw.rdy))
            yield mw.ack.eq(0)
            yield Tick()
            self.assertEqual(0xAA, (yield mw.sysmem[0]))

        self.simTestbench(bench, [0x0000, 0x0000])

    def test_simple_off(self):
        def bench(mw):
            yield mw.width.eq(AccessWidth.BYTE)
            yield mw.addr.eq(1)
            yield mw.data.eq(0xAAAAAAAA)
            self.waitFor(mw.rdy, change_to=1, ticks=1)
            yield mw.ack.eq(1)
            yield Tick()
            self.assertTrue((yield mw.rdy))
            yield mw.ack.eq(0)
            yield Tick()
            self.assertEqual(0xAA00, (yield mw.sysmem[0]))

        self.simTestbench(bench, [0x0000, 0x0000])

    def test_16(self):
        def bench(mw):
            yield mw.width.eq(AccessWidth.HALF)
            yield mw.addr.eq(0)
            yield mw.data.eq(0xAAAAAAAA)
            self.waitFor(mw.rdy, change_to=1, ticks=1)
            yield mw.ack.eq(1)
            yield Tick()
            self.assertTrue((yield mw.rdy))
            yield mw.ack.eq(0)
            yield Tick()
            self.assertEqual(0xAAAA, (yield mw.sysmem[0]))
            self.assertEqual(0x0000, (yield mw.sysmem[1]))

        self.simTestbench(bench, [0x0000, 0x0000])

    def test_16_off(self):
        def bench(mw):
            yield mw.width.eq(AccessWidth.HALF)
            yield mw.addr.eq(3)
            yield mw.data.eq(0xAAAAAAAA)
            self.waitFor(mw.rdy, change_to=1, ticks=1)
            yield mw.ack.eq(1)
            yield Tick()
            self.assertFalse((yield mw.rdy))
            yield mw.ack.eq(0)
            yield Tick()
            self.assertTrue((yield mw.rdy))
            yield Tick()
            self.assertEqual(0x0000, (yield mw.sysmem[0]))
            self.assertEqual(0xAA00, (yield mw.sysmem[1]))
            self.assertEqual(0x00AA, (yield mw.sysmem[2]))

        self.simTestbench(bench, [0x0000, 0x0000, 0x0000])
