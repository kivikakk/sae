import unittest

from . import FaultCode
from .test_utils import run_until_fault


class TestTop(unittest.TestCase):
    def test_top(self):
        run_until_fault([0xFFFF])
