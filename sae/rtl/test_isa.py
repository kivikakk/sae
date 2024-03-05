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
        self.assertEqual(unsigned(32), Shape.cast(RV32I.R.shape))
        self.assertEqual(("opcode", "rd", "imm"), RV32I.U.layout)

        self.assertEqual({"opcode": RV32I.Opcode.OP}, RV32I.R.values)

    def test_missing_len(self):
        with self.assertRaisesRegex(
            ValueError, r"^'sae\..*\.I\.IL' missing len, and no default given\.$"
        ):

            class I(ISA):
                class IL(ISA.ILayout):
                    layout = (1,)

    def test_bad_tuple(self):
        with self.assertRaisesRegex(
            TypeError, r"^Expected tuple for 'sae\..*\.I\.X', not str\.$"
        ):

            class I(ISA):
                class X(ISA.ILayout, len=1):
                    layout = "abc"  # i.e. ("abc") typed instead of ("abc",)

    def test_bad_field(self):
        with self.assertRaisesRegex(
            TypeError, r"^Unknown field specifier \[\] in layout of 'sae\..*\.I\.X'\.$"
        ):

            class I(ISA):
                class X(ISA.ILayout, len=1):
                    layout = ([], "abc")

    def test_unregistered(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^Field specifier 'abc' not registered, and "
            r"no 'resolve' implementation available\.$",
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

    def test_value_default_overlap(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^'sae\..*\.I\.IL' sets the following in both 'values' and 'defaults': \['b', 'c'\]\.$",
        ):

            class I(ISA):
                class IL(ISA.ILayout, len=12):
                    a: 4
                    b: 4
                    c: 4

                    layout = ("a", "b", "c")
                    values = {"a": 1, "b": 2, "c": 3}
                    defaults = {"b": 4, "c": 5}

    def test_default_missing_annotation(self):
        with self.assertRaisesRegex(
            TypeError,
            r"^Cannot resolve default value for element of 'sae\..*\.I\.IL': 'b'='X'\.$",
        ):

            class I(ISA):
                class IL(ISA.ILayout, len=8):
                    a: 4

                    layout = ("a", ("b", 4))
                    values = {"a": 1}
                    defaults = {"b": "X"}


class TestISAInsns(unittest.TestCase):
    def test_base(self):
        self.assertEqual(
            0x00C5_8533,
            RV32I.ADD(rd=RV32I.Reg("a0"), rs1=RV32I.Reg("a1"), rs2=RV32I.Reg("a2")),
        )
        self.assertEqual(0x4000_50B3, RV32I.SRA(rd="x1", rs1=("x0"), rs2=("x0")))
        self.assertEqual(0x40A5_D513, RV32I.SRAI(rd="a0", rs1="a1", shamt=0b01010))
        self.assertEqual(0x0000_8067, RV32I.RET())
        self.assertEqual(0x0000_0503, RV32I.LB(rd="a0", rs1off=(0, "x0")))
        self.assertEqual(0x8330_000F, RV32I.FENCE_TSO())
        self.assertEqual(0x0010_0073, RV32I.EBREAK())
        self.assertEqual(0x00B5_0223, RV32I.SB(rs2="a1", rs1off=(4, "a0")))
        self.assertEqual(0xC562_35EF, RV32I.JAL(rd="a1", imm=0x0012_3456))
        self.assertEqual(0xC562_306F, RV32I.J_(imm=0x0012_3456))

    def test_base_li(self):
        self.assertEqual([0x1230_0593], RV32I.LI(rd="a1", imm=0x123))
        self.assertEqual([0x0000_15B7, 0x2345_8593], RV32I.LI(rd="a1", imm=0x1234))
        self.assertEqual(
            [0x1234_55B7, 0x4005_8593, 0x4005_8593], RV32I.LI(rd="a1", imm=0x1234_5800)
        )

    def test_call_nonleaf(self):
        with self.assertRaisesRegex(
            TypeError,
            r"^'sae\..*\.RV32I\.IL' called, but it's layoutless\.$",
        ):
            RV32I.IL(a=1)

    def test_bad_define(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^'sae\..*\.RV32I\.R' called with argument 'xyz', "
            r"which is not part of its layout\.$",
        ):
            RV32I.R(xyz=1)

    def test_bad_call(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^'sae\..*\.RV32I\.R' called with argument 'xyz', "
            r"which is not part of its IL's layout\.$",
        ):
            RV32I.R()(xyz=1)

    def test_bad_define_override(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^'opcode' is already defined for 'sae\..*\.RV32I\.R' and cannot "
            r"be overridden\.$",
        ):
            RV32I.R(opcode=1)

    def test_bad_call_override(self):
        with self.assertRaisesRegex(
            ValueError,
            r"^'opcode' is already defined for 'sae\..*\.RV32I\.R' and cannot "
            r"be overridden in thunk\.$",
        ):
            RV32I.R()(opcode=1)

    def test_call_insufficient(self):
        with self.assertRaisesRegex(
            TypeError,
            r"^'sae\..*\.RV32I\.ADD' called without supplying values "
            r"for arguments: \['rd', 'rs1', 'rs2'\]\.$",
        ):
            RV32I.ADD()


class TestISAInheritance(unittest.TestCase):
    def test_base(self):
        self.assertIs(RV32I.Reg, RV32IC.Reg)
        self.assertIs(RV32I.Reg, RV32IC.CR.shape["rs2"].shape)
        self.assertIs(RV32I.I, RV32IC.I)
        self.assertIs(RV32I.ADD, RV32IC.ADD)