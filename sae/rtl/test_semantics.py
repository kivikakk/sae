import unittest

from . import InsI, InsIS, Opcode, OpImmFunct, Reg, State, Top
from .test_utils import InsnTestHelpers, Unchanged

__all__ = ["TestInsns"]


class TestInsns(InsnTestHelpers, unittest.TestCase):
    def test_addi(self):
        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 3)
            self.Addi(Reg.X1, Reg.X2, 5)
        self.assertRegs(("x1", 3), ("x2", 8), ("rest", Unchanged))

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Addi(Reg.X1, Reg.X2, -2)
        self.assertRegs(("x1", 1), ("x2", -1), ("rest", Unchanged))

    def test_slti(self):
        pass
