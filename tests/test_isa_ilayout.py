import pytest
from amaranth import Shape, unsigned
from amaranth.lib.data import StructLayout

from sae.isa import ISA, ILayout, RegisterSpecifier
from sae.rtl.isa_rv32 import RV32I, RV32IC


def test_base():
    assert RV32I.R.__name__ == "R"
    assert RV32I.I.shape == StructLayout({
        "opcode": RV32I.Opcode,
        "rd": RV32I.Reg,
        "funct3": unsigned(3),
        "rs1": RV32I.Reg,
        "imm": unsigned(12),
    })
    assert Shape.cast(RV32I.R.shape) == unsigned(32)
    assert RV32I.U.layout == ("opcode", "rd", "imm")

    assert RV32I.R.defaults == {"opcode": RV32I.Opcode.OP, "funct7": 0}

def test_missing_len():
    with pytest.raises(ValueError,
                       match=r"^'tests\.test_isa_ilayout\..*\.I\.IL' missing len, "
                             r"and no default given\.$"):
        class I(ISA):
            class IL(ILayout):
                layout = (1,)

def test_bad_tuple():
    with pytest.raises(TypeError,
                       match=r"^Expected tuple for 'tests\.test_isa_ilayout\..*\.I\.X', "
                             r"not str\.$"):
        class I(ISA):
            class X(ILayout, len=1):
                layout = "abc"  # i.e. ("abc") typed instead of ("abc",)

def test_bad_field():
    with pytest.raises(TypeError,
                       match=r"^Unknown field specifier \[\] in layout of "
                             r"'tests\.test_isa_ilayout\..*\.I\.X'\.$"):
        class I(ISA):
            class X(ILayout, len=1):
                layout = ([], "abc")

def test_unregistered():
    with pytest.raises(ValueError,
                       match=r"^Field specifier 'abc' not registered, and "
                             r"no 'resolve' implementation available\.$"):
        class I(ISA):
            class X(ILayout, len=1):
                layout = ("abc",)

def test_inadequate():
    with pytest.raises(ValueError,
                       match=r"^Layout components are inadequate \(fills 7/8\)\.$"):
        class I(ISA):
            class X(ILayout, len=8):
                sh1: 4
                sh2: 3

                layout = ("sh1", "sh2")

def test_excessive():
    with pytest.raises(ValueError,
                       match=r"^Layout components are excessive \(fills 12/8\)\.$"):
        class I(ISA):
            class X(ILayout, len=8):
                sh1: 4
                sh2: 4
                sh3: 4

                layout = ("sh1", "sh2", "sh3")

def test_default_missing_annotation():
    with pytest.raises(TypeError,
                       match=r"^Cannot resolve default value for element of "
                             r"'tests\.test_isa_ilayout\..*\.I\.IL': 'b'='X'\.$"):
        class I(ISA):
            class IL(ILayout, len=8):
                a: 4

                layout = ("a", ("b", 4))
                defaults = {"b": "X"}

