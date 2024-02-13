import unittest

from . import State, Top
from .rv32 import Reg
from .test_utils import InsnTestHelpers

__all__ = ["TestInsns"]


class TestInsns(InsnTestHelpers, unittest.TestCase):
    def test_addi(self):
        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 3)
            self.Addi(Reg.X1, Reg.X2, 5)
        self.assertRegs(x1=3, x2=8)

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Addi(Reg.X1, Reg.X2, -2)
        self.assertRegs(x1=1, x2=-1)

        with self.Run():
            self.Addi(Reg.X0, Reg.X1, 1)
            self.Addi(Reg.X1, Reg.X2, -2)
            self.Addi(Reg.X2, Reg.X3, -3)
        self.assertRegs(x1=1, x2=-1, x3=-4)

    def test_slti(self):
        with self.Run():
            self.Slti(Reg.X0, Reg.X1, 0)
        self.assertRegs(x1=0)

        with self.Run():
            self.Slti(Reg.X0, Reg.X1, 1)
        self.assertRegs(x1=1)

        with self.Run():
            self.Slti(Reg.X0, Reg.X1, -1)
        self.assertRegs(x1=0)

    def test_sltiu(self):
        with self.Run(x1=1):
            self.Sltiu(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=0)

        with self.Run(x1=1):
            self.Sltiu(Reg.X1, Reg.X2, 2)
        self.assertRegs(x2=1)

        with self.Run(x1=1):
            self.Sltiu(Reg.X1, Reg.X2, -1)  # 2^32-1 > 1
        self.assertRegs(x2=1)

    def test_andi(self):
        with self.Run(x1=1):
            self.Andi(Reg.X1, Reg.X2, 3)
        self.assertRegs(x2=1)

        with self.Run(x1=-1):
            self.Andi(Reg.X1, Reg.X2, 3)
        self.assertRegs(x2=3)

        with self.Run(x1=3):
            self.Andi(Reg.X1, Reg.X2, -1)
        self.assertRegs(x2=3)

    def test_ori(self):
        with self.Run(x1=1):
            self.Ori(Reg.X1, Reg.X2, 2)
        self.assertRegs(x2=3)

        with self.Run(x1=1):
            self.Ori(Reg.X1, Reg.X2, -2)
        self.assertRegs(x2=-1)

        with self.Run(x1=-2):
            self.Ori(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=-1)

    def test_xori(self):
        with self.Run(x1=0xAAAAAAAA):
            self.Xori(Reg.X1, Reg.X2, -1)
        self.assertRegs(x2=0x55555555)

        with self.Run():
            self.Xori(Reg.X0, Reg.X1, -1)
        self.assertRegs(x1=-1)

        with self.Run(x1=0x555):
            self.Xori(Reg.X1, Reg.X2, 0x555)
        self.assertRegs(x2=0)

        with self.Run(x1=0xAAA):
            self.Xori(Reg.X1, Reg.X2, 0xAAA)  # sx to 0xFFFFFAAA
        self.assertRegs(x2=0xFFFFF000)

    def test_slli(self):
        with self.Run(x1=0x55555555):
            self.Slli(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=0xAAAAAAAA)

        with self.Run(x1=0x55555555):
            self.Slli(Reg.X1, Reg.X2, 2)
        self.assertRegs(x2=0x55555554)

        with self.Run(x1=0x55555555):
            self.Slli(Reg.X1, Reg.X2, 3)
        self.assertRegs(x2=0xAAAAAAA8)

        with self.Run(x1=0x55555555):
            self.Slli(Reg.X1, Reg.X2, 4)
        self.assertRegs(x2=0x55555550)

    def test_srli(self):
        with self.Run(x1=0x55555555):
            self.Srli(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=0x2AAAAAAA)

        with self.Run(x1=0x55555555):
            self.Srli(Reg.X1, Reg.X2, 2)
        self.assertRegs(x2=0x15555555)

    def test_srai(self):
        with self.Run(x1=0x55555555):
            self.Srai(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=0x2AAAAAAA)

        with self.Run(x1=0xAAAAAAAA):
            self.Srai(Reg.X1, Reg.X2, 1)
        self.assertRegs(x2=0xD5555555)

        with self.Run(x1=0xAAAAAAAA):
            self.Srai(Reg.X1, Reg.X2, 2)
        self.assertRegs(x2=0xEAAAAAAA)

        with self.Run(x1=0xAAAAAAAA):
            self.Srai(Reg.X1, Reg.X2, 3)
        self.assertRegs(x2=0xF5555555)

    def test_lui(self):
        with self.Run():
            self.Lui(Reg.X1, 0x12345)
        self.assertRegs(x1=0x12345000)

        with self.Run():
            self.Lui(Reg.X1, 0xFFFFF)
        self.assertRegs(x1=0xFFFFF000)

    def test_auipc(self):
        with self.Run():
            self.Addi(Reg.X0, Reg.X0, 0)  # NOP
            self.Addi(Reg.X0, Reg.X0, 0)
            self.Addi(Reg.X0, Reg.X0, 0)
            self.Auipc(Reg.X1, 0x12345)
        self.assertRegs(x1=0x1234500C)  # I think.
