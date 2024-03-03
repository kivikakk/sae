from __future__ import annotations

import re

from amaranth import unsigned
from amaranth.lib.enum import IntEnum

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

    class IL(ISA.ILayouts, len=32):
        opcode: Opcode
        rd: Reg
        rs1: Reg
        rs2: Reg

        # TODO: make a helper to stitch together multiple imm(\d+(_\d+)?) automagically.
        def resolve(
            il,
            name,
            *,
            functn=re.compile(r"\Afunct(\d+)\Z"),
            immsingle=re.compile(r"\Aimm(\d+)\Z"),
            immmulti=re.compile(r"\Aimm(\d+)_(\d+)\Z"),
        ):
            if m := functn.match(name):
                return unsigned(int(m[1]))
            if name == "imm":
                assert il.after == [], "don't know how to deal with non-last imm"
                return unsigned(il.remlen)
            if m := immmulti.match(name):
                top = int(m[1])
                bottom = int(m[2])
                assert top > bottom, "immY_X format maps to imm[Y:X], Y must be > X"
                return unsigned(top - bottom + 1)
            if m := immsingle.match(name):
                return unsigned(1)
            assert False, f"unhandled: {name!r}"

        R = ("opcode", "rd", "funct3", "rs1", "rs2", "funct7")
        I = ("opcode", "rd", "funct3", "rs1", "imm")
        S = ("opcode", "imm4_0", "funct3", "rs1", "rs2", "imm11_5")
        B = ("opcode", "imm11", "imm4_1", "funct3", "rs1", "rs2", "imm10_5", "imm12")
        U = ("opcode", "rd", "imm")
        J = ("opcode", "rd", "imm19_12", "imm11", "imm10_1", "imm20")


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

    class IL(ISA.ILayouts, len=16):
        op: Op
        rs2: Reg
        rdrs1: Reg
        rd_: Reg_
        rs1_: Reg_
        rs2_: Reg_
        rd_rs1_: Reg_
        jump_target: unsigned(11)

        def resolve(
            il,
            name,
            *,
            functn=re.compile(r"\Afunct(\d+)\Z"),
        ):
            if m := functn.match(name):
                return unsigned(int(m[1]))
            assert False, f"unhandled: {name!r}"

        CR = ("op", "rs2", "rdrs1", "funct4")
        CI = ("op", ("imm", 5), "rdrs1", ("imm2", 1), "funct3")
        CSS = ("op", "rs2", ("imm", 6), "funct3")
        CIW = ("op", "rd_", ("imm", 8), "funct3")
        CL = ("op", "rd_", ("imm", 2), "rs1_", ("imm2", 3), "funct3")
        CS = ("op", "rs2_", ("imm", 2), "rs1_", ("imm2", 3), "funct3")
        CA = ("op", "rs2_", "funct2", "rd_rs1_", "funct6")
        CB = ("op", ("offset", 5), "rs1_", ("offset2", 3), "funct3")
        CJ = ("op", "jump_target", "funct3")
