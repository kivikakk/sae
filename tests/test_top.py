import unittest
from pathlib import Path

from sae.rtl.hart import FaultCode
from sae.rtl.rv32 import Reg

from .test_utils import run_until_fault


class TestTop(unittest.TestCase):
    def test_top(self):
        run_until_fault([0xFFFF])

    def test_rv_build(self):
        results = run_until_fault(Path(__file__).parent / "test_shrimple.bin")
        self.assertEqual(FaultCode.PC_MISALIGNED, FaultCode(results["faultcode"]))
        self.assertEqual(69, results[Reg("A0")])
        self.assertEqual(b"i am ur princess\r\n", results["uart"])
