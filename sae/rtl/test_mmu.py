import inspect
import unittest
from functools import partial, wraps

from amaranth import Fragment
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick
from rainhdx import Platform

from .mmu import MMU, AccessWidth
from .test_utils import print_mmu


def mmu_sim(inner):
    first_self = next(iter(inspect.signature(inner).parameters))

    @wraps(inner)
    def wrapper(*args, **kwargs):
        args = list(args)
        init = args.pop(1 if first_self else 0)

        mmu = MMU(sysmem=Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(Fragment.get(mmu, platform=Platform["test"]))
        sim.add_clock(1e-6)
        sim.add_testbench(partial(inner, *args, mmu=mmu, **kwargs))
        sim.run()

    return wrapper


class TestMMU(unittest.TestCase):
    def waitFor(self, mmu, s, *, change_to, ticks):
        for i in range(ticks):
            yield from print_mmu(mmu, prefix=f"  waitFor ({i}/{ticks}) -- ")
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
        yield from print_mmu(mmu, prefix=f"  waitFor ({ticks}/{ticks}) -- ")

    @mmu_sim
    def assertRead(self, addr, width, value, *, mmu):
        ticks = 2
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        assert ((yield mmu.read.rdy))
        yield mmu.read.addr.eq(addr)
        yield mmu.read.width.eq(width)
        yield mmu.read.ack.eq(1)
        yield Tick()
        yield mmu.read.ack.eq(0)
        yield from self.waitFor(mmu, mmu.read.valid, change_to=1, ticks=ticks)
        self.assertEqual(value, (yield mmu.read.value))

    @mmu_sim
    def assertWrite(self, addr, width, value, omem, *, mmu):
        ticks = 0
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        yield mmu.write.width.eq(width)
        yield mmu.write.addr.eq(addr)
        yield mmu.write.data.eq(value)
        yield from self.waitFor(mmu, mmu.write.rdy, change_to=1, ticks=1)
        yield mmu.write.ack.eq(1)
        yield Tick()
        yield mmu.write.ack.eq(0)
        yield from self.waitFor(mmu, mmu.write.rdy, change_to=1, ticks=ticks)
        yield Tick()
        for i, (ex, s) in enumerate(zip(omem, mmu.sysmem)):
            self.assertEqual(
                ex,
                (yield s),
                f"failed at index {i}: omem {ex:0>4x} != sysmem {(yield s):0>4x}",
            )

    def test_read(self):
        mem = [0x1234, 0xABCD]
        self.assertRead(mem, 0x00, AccessWidth.BYTE, 0x34)
        self.assertRead(mem, 0x01, AccessWidth.BYTE, 0x12)
        self.assertRead(mem, 0x02, AccessWidth.BYTE, 0xCD)
        self.assertRead(mem, 0x03, AccessWidth.BYTE, 0xAB)
        self.assertRead(mem, 0x00, AccessWidth.HALF, 0x1234)
        self.assertRead(mem, 0x01, AccessWidth.HALF, 0xCD12)
        self.assertRead(mem, 0x02, AccessWidth.HALF, 0xABCD)
        self.assertRead(mem, 0x03, AccessWidth.HALF, 0x34AB)
        self.assertRead(mem, 0x00, AccessWidth.WORD, 0xABCD1234)
        self.assertRead(mem, 0x01, AccessWidth.WORD, 0x34ABCD12)
        self.assertRead(mem, 0x02, AccessWidth.WORD, 0x1234ABCD)
        self.assertRead(mem, 0x03, AccessWidth.WORD, 0xCD1234AB)

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
