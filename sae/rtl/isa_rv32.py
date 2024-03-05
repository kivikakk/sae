from __future__ import annotations

import re
from functools import partial

from amaranth import unsigned
from amaranth.lib.enum import IntEnum

from .. import st
from .isa import ISA

__all__ = ["RV32I", "RV32IC"]


class RV32I(ISA):
    class Opcode(IntEnum, shape=7):
        LOAD = 0b0000011
        LOAD_FP = 0b0000111
        MISC_MEM = 0b0001111
        OP_IMM = 0b0010011
        AUIPC = 0b0010111
        OP_IMM_32 = 0b0011011
        STORE = 0b0100011
        STORE_FP = 0b0100111
        AMO = 0b0101111
        OP = 0b0110011
        LUI = 0b0110111
        OP_32 = 0b0111011
        MADD = 0b1000011
        MSUB = 0b1000111
        NMSUB = 0b1001011
        NMADD = 0b1001111
        OP_FP = 0b1010011
        BRANCH = 0b1100011
        JALR = 0b1100111
        JAL = 0b1101111
        SYSTEM = 0b1110011

    Reg = ISA.RegisterSpecifier(
        5,
        [
            ("zero", "x0"),
            ("ra", "x1"),
            ("sp", "x2"),
            ("gp", "x3"),
            ("tp", "x4"),
            ("t0", "x5"),
            ("t1", "x6"),
            ("t2", "x7"),
            ("fp", "s0", "x8"),
            ("s1", "x9"),
            ("a0", "x10"),
            ("a1", "x11"),
            ("a2", "x12"),
            ("a3", "x13"),
            ("a4", "x14"),
            ("a5", "x15"),
            ("a6", "x16"),
            ("a7", "x17"),
            ("s2", "x18"),
            ("s3", "x19"),
            ("s4", "x20"),
            ("s5", "x21"),
            ("s6", "x22"),
            ("s7", "x23"),
            ("s8", "x24"),
            ("s9", "x25"),
            ("s10", "x26"),
            ("s11", "x27"),
            ("t3", "x28"),
            ("t4", "x29"),
            ("t5", "x30"),
            ("t6", "x31"),
        ],
    )

    class IL(ISA.ILayout, len=32):
        opcode: Opcode
        rd: Reg
        rs1: Reg
        rs2: Reg

        # TODO: make a helper to stitch together multiple imm(\d+(_\d+)?) automagically.
        def resolve(
            name,
            *,
            after,
            remlen,
            functn=re.compile(r"\Afunct(\d+)\Z"),
            immsingle=re.compile(r"\Aimm(\d+)\Z"),
            immmulti=re.compile(r"\Aimm(\d+)_(\d+)\Z"),
        ):
            if m := functn.match(name):
                return unsigned(int(m[1]))
            if name == "imm":
                assert not after, "don't know how to deal with non-last imm"
                return unsigned(remlen)
            if m := immmulti.match(name):
                top = int(m[1])
                bottom = int(m[2])
                assert top > bottom, "immY_X format maps to imm[Y:X], Y must be > X"
                return unsigned(top - bottom + 1)
            if m := immsingle.match(name):
                return unsigned(1)
            assert False, f"unhandled: {name!r}"

    class R(IL):
        layout = ("opcode", "rd", "funct3", "rs1", "rs2", "funct7")
        values = {"opcode": "OP"}
        defaults = {"funct7": 0}

        class Funct(IntEnum, shape=3):
            ADDSUB = 0b000
            SLT = 0b010
            SLTU = 0b011
            AND = 0b111
            OR = 0b110
            XOR = 0b100
            SLL = 0b001
            SR = 0b101

        F7Negate = 0b0100000

    ADD = R(funct3=R.Funct.ADDSUB)
    SLT = R(funct3=R.Funct.SLT)
    SLTU = R(funct3=R.Funct.SLTU)
    AND = R(funct3=R.Funct.AND)
    OR = R(funct3=R.Funct.OR)
    XOR = R(funct3=R.Funct.XOR)
    SLL = R(funct3=R.Funct.SLL)
    SRL = R(funct3=R.Funct.SR)
    SUB = ADD.partial(funct7=R.F7Negate)
    SRA = SRL.partial(funct7=R.F7Negate)

    SNEZ = SLTU.partial(rs1="zero")

    class I(IL):
        layout = ("opcode", "rd", "funct3", "rs1", "imm")
        defaults = {"opcode": "OP_IMM"}

        class IFunct(IntEnum, shape=3):
            ADDI = 0b000
            SLTI = 0b010
            SLTIU = 0b011
            XORI = 0b100
            ORI = 0b110
            ANDI = 0b111
            SLLI = 0b001
            SRI = 0b101

        class LFunct(IntEnum, shape=3):
            # Note the bottom 2 bits convey the size the same as AccessWidth.
            LB = 0b000
            LH = 0b001
            LW = 0b010
            LBU = 0b100
            LHU = 0b101

    ADDI = I(funct3=I.IFunct.ADDI)
    SLTI = I(funct3=I.IFunct.SLTI)
    SLTIU = I(funct3=I.IFunct.SLTIU)
    XORI = I(funct3=I.IFunct.XORI)
    ORI = I(funct3=I.IFunct.ORI)
    ANDI = I(funct3=I.IFunct.ANDI)

    @staticmethod
    def shamt_xfrm(shamt, *, imm11_5=0):
        assert 0 <= shamt < 2**5, f"shamt is {shamt!r}"
        return {"imm": (imm11_5 << 5) | shamt}

    SLLI = I(funct3=I.IFunct.SLLI).xfrm(shamt_xfrm)
    SRLI = I(funct3=I.IFunct.SRI).xfrm(shamt_xfrm)
    SRAI = I(funct3=I.IFunct.SRI).xfrm(partial(shamt_xfrm, imm11_5=0b0100000))

    JALR = I(opcode="JALR", funct3=0)
    RET = JALR.partial(rd="zero", rs1="ra", imm=0)

    @staticmethod
    def rs1off_xfrm(rs1off):
        """
        Transforms "rs1off" to an (offset, reg) pair.

        * Passes through an (offset, reg) pair unchanged.
        * Parses an (offset, regstr) pair.
        *
        """
        match rs1off:
            case (int(), RV32I.Reg()):
                return {"imm": rs1off[0], "rs1": rs1off[1]}
            case (int(), str()):
                return {"imm": rs1off[0], "rs1": RV32I.Reg(rs1off[1])}
            case st.Offset():
                return {
                    "imm": rs1off.offset,
                    "rs1": RV32I.Reg(rs1off.register.register),
                }
            case _:
                assert False, f"unknown rs1off {rs1off!r}"

    LB = I(opcode="LOAD", funct3=I.LFunct.LB).xfrm(rs1off_xfrm)

    class S(IL):
        layout = ("opcode", "imm4_0", "funct3", "rs1", "rs2", "imm11_5")

    class B(IL):
        layout = (
            "opcode",
            "imm11",
            "imm4_1",
            "funct3",
            "rs1",
            "rs2",
            "imm10_5",
            "imm12",
        )

    class U(IL):
        layout = ("opcode", "rd", "imm")

    class J(IL):
        layout = ("opcode", "rd", "imm19_12", "imm11", "imm10_1", "imm20")


class RV32IC(RV32I):
    class Op(IntEnum, shape=2):
        C0 = 0b00
        C1 = 0b01
        C2 = 0b10

    Reg_ = ISA.RegisterSpecifier(
        3,
        [
            ("s0", "x8"),
            ("s1", "x9"),
            ("a0", "x10"),
            ("a1", "x11"),
            ("a2", "x12"),
            ("a3", "x13"),
            ("a4", "x14"),
            ("a5", "x15"),
        ],
    )

    class IL(ISA.ILayout, len=16):
        op: Op
        rs2: Reg
        rdrs1: Reg
        rd_: Reg_
        rs1_: Reg_
        rs2_: Reg_
        rd_rs1_: Reg_

        def resolve(
            name,
            *,
            functn=re.compile(r"\Afunct(\d+)\Z"),
            **_,
        ):
            if m := functn.match(name):
                return unsigned(int(m[1]))
            assert False, f"unhandled: {name!r}"

    class CR(IL):
        layout = ("op", "rs2", "rdrs1", "funct4")

    class CI(IL):
        layout = ("op", ("imm", 5), "rdrs1", ("imm2", 1), "funct3")

    class CSS(IL):
        layout = ("op", "rs2", ("imm", 6), "funct3")

    class CIW(IL):
        layout = ("op", "rd_", ("imm", 8), "funct3")

    class CL(IL):
        layout = ("op", "rd_", ("imm", 2), "rs1_", ("imm2", 3), "funct3")

    class CS(IL):
        layout = ("op", "rs2_", ("imm", 2), "rs1_", ("imm2", 3), "funct3")

    class CA(IL):
        layout = ("op", "rs2_", "funct2", "rd_rs1_", "funct6")

    class CB(IL):
        layout = ("op", ("offset", 5), "rs1_", ("offset2", 3), "funct3")

    class CJ(IL):
        jump_target: unsigned(11)

        layout = ("op", "jump_target", "funct3")
