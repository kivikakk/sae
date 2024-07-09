import pytest

from sae.rtl.isa_rv32 import RV32I


def test_base():
    assert RV32I.ADD.value(rd=RV32I.Reg("a0"), rs1=RV32I.Reg("a1"), rs2=RV32I.Reg("a2")) == 0x00C5_8533
    assert RV32I.SRA.value(rd="x1", rs1=("x0"), rs2=("x0")) == 0x4000_50B3
    assert RV32I.SRAI.value(rd="a0", rs1="a1", shamt=0b01010) == 0x40A5_D513
    assert RV32I.RET.value() == 0x0000_8067
    assert RV32I.LB.value(rd="a0", rs1off=(0, "x0")) == 0x0000_0503
    assert RV32I.FENCE_TSO.value() == 0x8330_000F
    assert RV32I.EBREAK.value() == 0x0010_0073
    assert RV32I.SB.value(rs2="a1", rs1off=(4, "a0")) == 0x00B5_0223
    assert RV32I.JAL.value(rd="a1", imm=0x0012_3456) == 0xC562_35EF
    assert RV32I.J_.value(imm=0x0012_3456) == 0xC562_306F


def test_base_li():
    assert RV32I.LI.value(rd="a1", imm=0x123) == 0x1230_0593
    assert RV32I.LI.value(rd="a1", imm=0x1234) == [0x0000_15B7, 0x2345_8593]
    assert RV32I.LI.value(rd="a1", imm=0x1234_5800) == [0x1234_55B7, 0x4005_8593, 0x4005_8593]


def test_call_nonleaf():
    with pytest.raises(TypeError,
                       match=r"^'sae\..*\.RV32I\.IL' called, but it's layoutless\.$"):
        RV32I.IL(a=1)


def test_bad_define():
    with pytest.raises(ValueError,
                       match=r"^'sae\..*\.RV32I\.R child' given invalid argument 'xyz'."):
        RV32I.R(xyz=1)


def test_bad_call():
    with pytest.raises(ValueError,
                       match=r"^'sae\..*\.RV32I\.R child' called with argument 'xyz', "
                             r"which is not part of its layout\.$"):
        RV32I.R().value(xyz=1)


def test_bad_call_override():
    with pytest.raises(ValueError,
                       match=r"^'opcode' is already defined for 'sae\..*\.RV32I\.R child' "
                             r"and cannot be overridden\.$"):
        RV32I.R().value(opcode=1)


def test_call_insufficient():
    with pytest.raises(TypeError,
                       match=r"^'sae\..*\.RV32I\.ADD' called without supplying values "
                             r"for arguments: \['rd', 'rs1', 'rs2'\]\.$"):
        RV32I.ADD.value()


def test_match_simple():
    # SUB only differs from ADD by funct7.
    kwargs = {"rd": RV32I.Reg("a0"), "rs1": RV32I.Reg("a1"), "rs2": RV32I.Reg("a2")}
    v = RV32I.ADD.value(**kwargs)
    assert RV32I.ADD.match_value(v) == kwargs
    assert RV32I.SUB.match_value(v) is None

    v = RV32I.SUB.value(**kwargs)
    assert RV32I.SUB.match_value(v) == kwargs
    assert RV32I.ADD.match_value(v) is None

    # SNEZ is SLTU(rs1="zero").
    v = RV32I.SLTU.value(**kwargs)
    assert RV32I.SLTU.match_value(v) == kwargs
    assert RV32I.SNEZ.match_value(v) is None

    kwargs["rs1"] = RV32I.Reg("zero")
    kwargs_without_rs1 = kwargs.copy()
    kwargs_without_rs1.pop("rs1")
    v = RV32I.SLTU.value(**kwargs)
    assert RV32I.SLTU.match_value(v) == kwargs
    assert RV32I.SNEZ.match_value(v) == kwargs_without_rs1
