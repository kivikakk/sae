import unittest

from . import State, Top, test_utils


class TestTop(unittest.TestCase):
    def test_top(self):
        test_utils.run_until_fault(Top())
