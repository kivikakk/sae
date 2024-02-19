import unittest

from amaranth import Memory

from . import FaultCode, State, Top
from .rv32 import Reg
from .test_utils import run_until_fault


class TestTop(unittest.TestCase):
    def test_top(self):
        run_until_fault(Top(sysmem=Memory(width=16, depth=1, init=[0xFFFF])))

    def test_lluvia(self):
        results = run_until_fault(Top(reg_inits={"x1": 0xFFFF_FFFF}))
        self.assertEqual(FaultCode.PC_MISALIGNED, results["faultcode"])
        self.assertEqual(123, results[Reg("A0")])
