import unittest
from functools import partial

from amaranth import Fragment
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick
from rainhdx import Platform

from .mmu import MMU, AccessWidth
from .test_utils import print_mmu


class TestMMU(unittest.TestCase):
    def waitFor(self, s, *, change_to, ticks, mr=None, mw=None, sysmem=None):
        for i in range(ticks):
            if mr or mw:
                yield from print_mmu(
                    mr=mr, mw=mw, sysmem=sysmem, prefix=f"  waitFor ({i}/{ticks}) -- "
                )
            self.assertNotEqual(
                change_to,
                (yield s),
                f"{s} changed to {change_to} after {i} tick(s) (out of {ticks})",
            )
            yield Tick()
        self.assertEqual(
            change_to,
            (yield s),
            f"{s} didn't change to {change_to} after {ticks} tick(s)",
        )
        if mr or mw:
            yield from print_mmu(
                mr=mr, mw=mw, sysmem=sysmem, prefix=f"  waitFor ({ticks}/{ticks}) -- "
            )

    def assertRead(self, addr, width, value, mem):
        ticks = 2
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        def bench(*, mmu, _mr, _mw):
            assert ((yield mmu.read.rdy))
            yield mmu.read.addr.eq(addr)
            yield mmu.read.width.eq(width)
            yield mmu.read.ack.eq(1)
            yield Tick()
            yield mmu.read.ack.eq(0)
            yield from self.waitFor(
                mmu.read.valid, change_to=1, ticks=ticks, mr=_mr, sysmem=mmu.sysmem
            )
            self.assertEqual(value, (yield mmu.read.value))

        self.simTestbench(bench, mem)

    def assertWrite(self, imem, addr, width, value, omem):
        ticks = 0
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        def bench(*, mmu, _mw, _mr):
            yield mmu.write.width.eq(width)
            yield mmu.write.addr.eq(addr)
            yield mmu.write.data.eq(value)
            yield from self.waitFor(
                mmu.write.rdy, change_to=1, ticks=1, mw=_mw, sysmem=mmu.sysmem
            )
            yield mmu.write.ack.eq(1)
            yield Tick()
            yield mmu.write.ack.eq(0)
            yield from self.waitFor(
                mmu.write.rdy, change_to=1, ticks=ticks, mw=_mw, sysmem=mmu.sysmem
            )
            yield Tick()
            for i, (ex, s) in enumerate(zip(omem, mmu.sysmem)):
                self.assertEqual(
                    ex,
                    (yield s),
                    f"failed at index {i}: omem {ex:0>4x} != sysmem {(yield s):0>4x}",
                )

        self.simTestbench(bench, imem)

    def simTestbench(self, bench, init):
        mmu = MMU(sysmem=Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(Fragment.get(mmu, platform=Platform["test"]))
        sim.add_clock(1e-6)
        sim.add_testbench(partial(bench, mmu=mmu, _mr=mmu.mmu_read, _mw=mmu.mmu_write))
        sim.run()

    def test_read(self):
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

    def test_write(self):
        mem = [0xABCD, 0xEFFE]
        self.assertWrite(mem, 0, AccessWidth.BYTE, 0x12345678, [0xAB78, 0xEFFE])
        self.assertWrite(mem, 1, AccessWidth.BYTE, 0x12345678, [0x78CD, 0xEFFE])
        self.assertWrite(mem, 2, AccessWidth.BYTE, 0x12345678, [0xABCD, 0xEF78])
        self.assertWrite(mem, 3, AccessWidth.BYTE, 0x12345678, [0xABCD, 0x78FE])
        self.assertWrite(mem, 0, AccessWidth.HALF, 0x12345678, [0x5678, 0xEFFE])
        self.assertWrite(mem, 1, AccessWidth.HALF, 0x12345678, [0x78CD, 0xEF56])
        self.assertWrite(mem, 2, AccessWidth.HALF, 0x12345678, [0xABCD, 0x5678])
        self.assertWrite(mem, 3, AccessWidth.HALF, 0x12345678, [0xAB56, 0x78FE])
        self.assertWrite(mem, 0, AccessWidth.WORD, 0x12345678, [0x5678, 0x1234])
        self.assertWrite(mem, 1, AccessWidth.WORD, 0x12345678, [0x7812, 0x3456])
        self.assertWrite(mem, 2, AccessWidth.WORD, 0x12345678, [0x1234, 0x5678])
        self.assertWrite(mem, 3, AccessWidth.WORD, 0x12345678, [0x3456, 0x7812])
