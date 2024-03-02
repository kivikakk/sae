import unittest

from .isa import ISA, RV32I


class TestISARegs(unittest.TestCase):
    def test_base(self):
        self.assertEqual("Reg", RV32I.Reg.__name__)

        x0 = RV32I.Reg("x0")
        self.assertEqual(0, x0)
        self.assertEqual(["ZERO", "X0"], x0.aliases)
        self.assertIs(x0, RV32I.Reg("Zero"))

    def test_exhaustive(self):
        with self.assertRaisesRegex(
            ValueError, r"^Register naming isn't exhaustive\.$"
        ):
            ISA.RegisterSpecifier(2, ["a", "b", "c"])

    def test_excessive(self):
        with self.assertRaisesRegex(ValueError, r"^Register naming is excessive\.$"):
            ISA.RegisterSpecifier(1, ["a", "b", "c"])

    def test_wonky(self):
        with self.assertRaisesRegex(TypeError, r"^Unknown name specifier \[\]\.$"):
            ISA.RegisterSpecifier(1, ["a", []])


class TestISAILayouts(unittest.TestCase):
    def test_base(self):
        self.assertEqual("I", RV32I.I.__name__)

        self.assertEqual(32, RV32I.I.size)

    def test_no_len(self):
        with self.assertRaisesRegex(
            ValueError, r"^ILayout needs a len, and no default is set\.$"
        ):
            with ISA.ILayouts() as il:
                il("xyz")

    def test_bad_field(self):
        with self.assertRaisesRegex(TypeError, r"^Unknown field specifier 2\.$"):
            with ISA.ILayouts() as il:
                il(1, 2)

    def test_unregistered(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^Field specifier 'abc' not registered, and no default type function given\.$",
        ):
            with ISA.ILayouts() as il:
                il.default(len=1)
                il("abc")
