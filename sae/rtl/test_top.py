import unittest
from amaranth.sim import Simulator, Tick

from . import Top, State


class TestTop(unittest.TestCase):
    def test_top(self):
        top = Top()

        def bench():
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

        sim = Simulator(top)
        sim.add_clock(1e6)
        sim.add_testbench(bench)
        sim.run()
