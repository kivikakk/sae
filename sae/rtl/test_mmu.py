import unittest
from functools import partial

from amaranth import Elaboratable, Module
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick

from .mmu import AccessWidth, MMURead


def pms(mr):
    print(
        f"MMUR: [{(yield mr.state):0>1x}] addr={(yield mr.addr):0>8x}  width={AccessWidth((yield mr.width))}  "
        f"value={(yield mr.value):0>8x}  valid={(yield mr.valid):b}"
    )


class TestMMURead(unittest.TestCase):
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

    def simTestbench(self, bench, init):
        mr = MMURead(Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(mr)
        sim.add_clock(1e-6)
        sim.add_testbench(partial(bench, mr))
        sim.run()

    def test_simple(self):
        def bench(mr):
            self.assertEqual(0, (yield mr.addr))
            self.assertEqual(AccessWidth.BYTE, (yield mr.width))
            yield from self.waitFor(mr.valid, change_to=1, ticks=3)
            self.assertEqual(0x34, (yield mr.value))

        self.simTestbench(bench, [0x1234, 0xABCD])

    def test_rejig(self):
        def bench(mr):
            yield Tick()  # I'm kinda annoyed I need this?  But it doesn't repro otherwise ...
            self.assertEqual(AccessWidth.BYTE, (yield mr.width))
            yield mr.width.eq(AccessWidth.WORD)
            yield from self.waitFor(mr.valid, change_to=1, ticks=6)
            self.assertEqual(0xABCD1234, (yield mr.value))

        self.simTestbench(bench, [0x1234, 0xABCD, 0x5678, 0xEF01])
