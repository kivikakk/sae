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

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Addi(Reg.X1, Reg.X2, -2)
            self.Addi(Reg.X2, Reg.X3, -3)
        self.assertRegs(("x1", 1), ("x2", -1), ("x3", -4), ("rest", Unchanged))

    def test_slti(self):
        with self.Run():
            self.Slti(Reg.X0, Reg.X1, 0)
        self.assertRegs(("x1", 0), ("rest", Unchanged))

        with self.Run():
            self.Slti(Reg.X0, Reg.X1, 1)
        self.assertRegs(("x1", 1))

        with self.Run():
            self.Slti(Reg.X0, Reg.X1, -1)
        self.assertRegs(("x1", 0))

    def test_sltiu(self):
        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Sltiu(Reg.X1, Reg.X2, 1)
        self.assertRegs(("x1", 1), ("x2", 0), ("rest", Unchanged))

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Sltiu(Reg.X1, Reg.X2, 2)
        self.assertRegs(("x1", 1), ("x2", 1), ("rest", Unchanged))

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Sltiu(Reg.X1, Reg.X2, -1)  # 2^32-1 > 1
        self.assertRegs(("x1", 1), ("x2", 1), ("rest", Unchanged))
