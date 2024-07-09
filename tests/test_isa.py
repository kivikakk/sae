import pytest

from sae.isa import RegisterSpecifier
from sae.rtl.isa_rv32 import RV32I, RV32IC


def test_reg():
    assert RV32I.Reg.__name__ == "Reg"

    x0 = RV32I.Reg("x0")
    assert x0 == 0
    assert x0.aliases == ["ZERO", "X0"]
    assert x0 is RV32I.Reg("Zero")


def test_reg_inadequate():
    with pytest.raises(ValueError, match=r"^Register naming is inadequate \(named 3/4\)\.$"):
        RegisterSpecifier(2, ["a", "b", "c"])


def test_reg_excessive():
    with pytest.raises(ValueError, match=r"^Register naming is excessive \(named 3/2\)\.$"):
        RegisterSpecifier(1, ["a", "b", "c"])


def test_reg_wonky():
    with pytest.raises(TypeError, match=r"^Unknown name specifier \[\]\.$"):
        RegisterSpecifier(1, ["a", []])


def test_inheritance():
    assert RV32IC.Reg is RV32I.Reg
    assert RV32IC.CR.shape["rs2"].shape is RV32I.Reg
    assert RV32IC.I is RV32I.I
    assert RV32IC.ADD is RV32I.ADD
