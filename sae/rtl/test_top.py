import unittest
from pathlib import Path

from amaranth.lib.memory import Memory

from . import FaultCode, State, Top
from .rv32 import Reg
from .test_utils import run_until_fault


class TestTop(unittest.TestCase):
    def test_top(self):
        run_until_fault([0xFFFF])

    def test_lluvia(self):
        results = run_until_fault(
            Path(__file__).parent / "test_shrimple.bin",
            reg_inits={"x1": 0xFFFF_FFFF},
        )
        self.assertEqual(FaultCode.PC_MISALIGNED, FaultCode(results["faultcode"]))
        self.assertEqual(123, results[Reg("A0")])
