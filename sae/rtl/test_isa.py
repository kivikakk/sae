import unittest

from .isa import ISA, RV32I


class TestISARegs(unittest.TestCase):
    def test_base(self):
        x0 = RV32I.Reg("x0")
        self.assertEqual(0, x0)
        self.assertEqual(["ZERO", "X0"], x0.aliases)
        self.assertIs(x0, RV32I.Reg("Zero"))

    def test_exhaustive(self):
        with self.assertRaisesRegex(ValueError, "Register naming isn't exhaustive."):
            ISA.RegisterSpecifier(2, ["a", "b", "c"])

    def test_excessive(self):
        with self.assertRaisesRegex(ValueError, "Register naming is excessive."):
            ISA.RegisterSpecifier(1, ["a", "b", "c"])
