from amaranth import Memory
from amaranth.sim import Simulator, Tick

from . import State, Top

__all__ = ["run_until_fault", "Unwritten", "InsnTestHelpers"]


def run_until_fault(top):
    results = {}

    def bench():
        nonlocal results
        first = True
        pc = None
        print()
        while State.RUNNING == (yield top.state):
            if first:
                first = False
            else:
                yield Tick()
            last_pc, pc = pc, (yield top.pc)
            if pc != last_pc:
                print(f"pc={pc:08x}  ", end="")
                for i in range(1, 6):
                    print(f"  x{i}={(yield top.xreg[i]):08x}", end="")
                print("    mem=", end="")
                for i in range(8):
                    v = yield top.sysmem[i]
                    print(f"{v:0>4x} ", end="")
                print("...")

        results["pc"] = yield top.pc
        for i in range(1, 32):
            if not top.track_reg_written or (yield top.xreg_written[i]):
                results[f"x{i}"] = yield top.xreg[i]

    sim = Simulator(top)
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results


class UnwrittenClass:
    def __repr__(self):
        return "Unwritten"


Unwritten = UnwrittenClass()


class InsnTestHelpers:
    def __init__(self, *args):
        super().__init__(*args)
        self.body = None
        self.results = None

    def run_body(self, regs):
        top = Top(
            sysmem=Memory(width=16, depth=len(self.body) + 2, init=self.body + [0, 0]),
            reg_inits=regs,
            track_reg_written=True,
        )
        self.results = run_until_fault(top)
        self.body = None
        self.__asserted = set(["pc"])

    def assertReg(self, xr, v):
        rn = f"x{int(xr)}"
        self.__asserted.add(rn)
        self.assertRegValue(v, self.results.get(rn, Unwritten))

    def assertRegRest(self, v):
        for name, result in self.results.items():
            if name in self.__asserted:
                continue
            self.assertRegValue(v, result)

    def assertRegValue(self, expected, actual):
        if expected is Unwritten or actual is Unwritten:
            self.assertIs(expected, actual)
            return
        if expected < 0:
            expected += 2**32  # XLEN
        self.assertEqual(
            expected, actual, f"expected 0x{expected:X}, actual 0x{actual:X}"
        )
