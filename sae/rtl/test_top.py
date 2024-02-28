import unittest
from pathlib import Path

from . import FaultCode
from .rv32 import Reg
from .test_utils import run_until_fault


class TestTop(unittest.TestCase):
    def test_top(self):
        run_until_fault([0xFFFF])
