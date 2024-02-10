import unittest
from amaranth.sim import Simulator

from . import Top


class TestTop(unittest.TestCase):
    def test_top(self):
        top = Top()

        def bench():
            print((yield top.pc))
            yield
            print((yield top.pc))

        sim = Simulator(top)
        sim.add_clock(1e6)
        sim.add_sync_process(bench)
        sim.run()
