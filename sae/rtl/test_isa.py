import unittest

from amaranth import Shape, unsigned
from amaranth.lib.data import StructLayout

from .isa import ISA
from .isa_rv32 import RV32I, RV32IC


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


class TestISAILayout(unittest.TestCase):
    def test_base(self):
        self.assertEqual("R", RV32I.R.__name__)
        self.assertEqual(
            StructLayout(
                {
                    "opcode": RV32I.Opcode,
                    "rd": RV32I.Reg,
                    "funct3": unsigned(3),
                    "rs1": RV32I.Reg,
                    "imm": unsigned(12),
                }
            ),
            RV32I.I.shape,
        )
        self.assertEqual(unsigned(32), Shape.cast(RV32I.R))
        self.assertEqual(("opcode", "rd", "imm"), RV32I.U.layout)

    def test_bad_field(self):
        with self.assertRaisesRegex(TypeError, r"^Unknown field specifier 1\.$"):

            class I(ISA):
                class IL(ISA.ILayout, len=1):
                    layout = (1, 2)

    def test_bad_tuple(self):
        with self.assertRaisesRegex(
            TypeError, r"^Expected tuple for 'sae.rtl.test_[^']+\.I\.X', not str\.$"
        ):

            class I(ISA):
                class X(ISA.ILayout, len=1):
                    layout = "abc"  # i.e. ("abc") typed instead of ("abc",)

    def test_unregistered(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^Field specifier 'abc' not registered, and no 'resolve' implementation available\.$",
        ):

            class I(ISA):
                class X(ISA.ILayout, len=1):
                    layout = ("abc",)

    def test_inadequate(self):
        with self.assertRaisesRegex(
            ValueError, r"^Layout components are inadequate \(fills 7/8\)\.$"
        ):

            class I(ISA):
                class X(ISA.ILayout, len=8):
                    sh1: 4
                    sh2: 3

                    layout = ("sh1", "sh2")

    def test_excessive(self):
        with self.assertRaisesRegex(
            ValueError, r"^Layout components are excessive \(fills 12/8\)\.$"
        ):

            class I(ISA):
                class X(ISA.ILayout, len=8):
                    sh1: 4
                    sh2: 4
                    sh3: 4

                    layout = ("sh1", "sh2", "sh3")


class TestISAInheritance(unittest.TestCase):
    def test_base(self):
        self.assertIs(RV32I.Reg, RV32IC.Reg)
        self.assertIs(RV32I.Reg, RV32IC.CR.shape["rs2"].shape)
        self.assertIs(RV32I.I, RV32IC.I)
