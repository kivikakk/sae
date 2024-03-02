import unittest

from .isa import ISA
from .isa_rv32 import RV32I


class TestISARegs(unittest.TestCase):
    def test_base(self):
        self.assertEqual("Reg", RV32I.Reg.__name__)

        x0 = RV32I.Reg("x0")
        self.assertEqual(0, x0)
        self.assertEqual(["ZERO", "X0"], x0.aliases)
        self.assertIs(x0, RV32I.Reg("Zero"))

    def test_inadequate(self):
        with self.assertRaisesRegex(
            ValueError, r"^Register naming is inadequate \(named 3/4\)\.$"
        ):
            ISA.RegisterSpecifier(2, ["a", "b", "c"])

    def test_excessive(self):
        with self.assertRaisesRegex(
            ValueError, r"^Register naming is excessive \(named 3/2\)\.$"
        ):
            ISA.RegisterSpecifier(1, ["a", "b", "c"])

    def test_wonky(self):
        with self.assertRaisesRegex(TypeError, r"^Unknown name specifier \[\]\.$"):
            ISA.RegisterSpecifier(1, ["a", []])


class TestISAILayouts(unittest.TestCase):
    def test_base(self):
        self.assertEqual("R", RV32I.IL.R.__name__)
        self.assertEqual(32, RV32I.IL.R.size)

    def test_bad_field(self):
        with self.assertRaisesRegex(TypeError, r"^Unknown field specifier 1\.$"):

            class I(ISA):
                class IL(ISA.ILayouts, len=1):
                    X = (1, 2)

    def test_unregistered(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^Field specifier 'abc' not registered, and no default type function given\.$",
        ):

            class I(ISA):
                class IL(ISA.ILayouts, len=1):
                    X = "abc"

    def test_inadequate(self):
        with self.assertRaisesRegex(
            ValueError, r"^Layout components are inadequate \(fills 7/8\)\.$"
        ):

            class I(ISA):
                class IL(ISA.ILayouts, len=8):
                    sh1: 4
                    sh2: 3

                    X = ("sh1", "sh2")

    def test_excessive(self):
        with self.assertRaisesRegex(
            ValueError, r"^Layout components are excessive \(fills 12/8\)\.$"
        ):

            class I(ISA):
                class IL(ISA.ILayouts, len=8):
                    sh1: 4
                    sh2: 4
                    sh3: 4

                    X = ("sh1", "sh2", "sh3")
