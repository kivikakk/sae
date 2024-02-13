from amaranth.sim import Simulator, Tick

from . import State

__all__ = ["run_until_fault"]


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
                for i in range(1, 4):
                    print(f"  x{i}={(yield top.xreg[i]):08x}", end="")
                print()

        results["pc"] = yield top.pc
        for i in range(1, 32):
            results[f"x{i}"] = yield top.xreg[i]

    sim = Simulator(top)
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results
