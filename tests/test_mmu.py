import unittest
from functools import partial, wraps

from amaranth import Fragment
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator

from sae.rtl.mmu import MMU, AccessWidth
from sae.targets import test

from .test_utils import print_mmu


def mmu_sim(inner):
    @wraps(inner)
    def wrapper(*args, **kwargs):
        args = list(args)
        init = args.pop(1) # after self.

        mmu = MMU(sysmem=Memory(depth=len(init), shape=16, init=init))
        sim = Simulator(Fragment.get(mmu, platform=test()))
        sim.add_clock(1e-6)
        sim.add_testbench(partial(inner, *args, mmu=mmu, **kwargs))
        sim.run()

    return wrapper


class TestMMU(unittest.TestCase):
    async def waitFor(self, ctx, mmu, s, *, change_to, ticks):
        for i in range(ticks):
            print_mmu(ctx, mmu, prefix=f"  waitFor ({i}/{ticks}) -- ")
            self.assertNotEqual(
                change_to,
                ctx.get(s),
                f"{s.name} changed to {change_to} after {i} tick(s) (out of {ticks})",
            )
            await ctx.tick()
        self.assertEqual(
            change_to,
            ctx.get(s),
            f"{s.name} didn't change to {change_to} after {ticks} tick(s)",
        )
        print_mmu(ctx, mmu, prefix=f"  waitFor ({ticks}/{ticks}) -- ")

    @mmu_sim
    async def assertRead(self, addr, width, value, ctx, *, mmu):
        ticks = 2
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        assert ctx.get(mmu.read.req.ready)
        ctx.set(mmu.read.req.payload.addr, addr)
        ctx.set(mmu.read.req.payload.width, width)
        ctx.set(mmu.read.req.valid, 1)
        await ctx.tick()
        ctx.set(mmu.read.req.valid, 0)
        await self.waitFor(
            ctx,
            mmu,
            mmu.read.resp.valid,
            change_to=1,
            ticks=ticks,
        )
        self.assertEqual(value, ctx.get(mmu.read.resp.payload))

    @mmu_sim
    async def assertWrite(self, addr, width, value, omem, ctx, *, mmu):
        ticks = 0
        if addr & 1 and width != AccessWidth.BYTE:
            ticks += 1
        if width == AccessWidth.WORD:
            ticks += 1

        ctx.set(mmu.write.req.payload.width, width)
        ctx.set(mmu.write.req.payload.addr, addr)
        ctx.set(mmu.write.req.payload.data, value)
        await self.waitFor(ctx, mmu, mmu.write.req.ready, change_to=1, ticks=1)
        ctx.set(mmu.write.req.valid, 1)
        await ctx.tick()
        ctx.set(mmu.write.req.valid, 0)
        await self.waitFor(ctx, mmu, mmu.write.req.ready, change_to=1, ticks=ticks)
        await ctx.tick()
        for i, (ex, s) in enumerate(zip(omem, mmu.sysmem.data)):
            self.assertEqual(
                ex,
                ctx.get(s),
                f"failed at index {i}: omem {ex:0>4x} != sysmem {ctx.get(s):0>4x}",
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
