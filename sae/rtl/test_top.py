import unittest

from amaranth import Memory

from . import State, Top, test_utils


class TestTop(unittest.TestCase):
    def test_top(self):
        test_utils.run_until_fault(
            Top(
                sysmem=Memory(
                    width=16,
                    depth=1,
                    init=[0xFFFF],
                )
            )
        )
