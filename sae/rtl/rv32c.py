from amaranth import unsigned
from amaranth.lib.data import Struct

from .rv32 import Reg

__all__ = [
    "InsCR",
    "InsCI",
    "InsCSS",
    "InsCIW",
    "InsCL",
    "InsCS",
    "InsCA",
    "InsCB",
    "InsCJ",
]


class Op(IntEnum, shape=2):  # type: ignore
    C0 = 0b00
    C1 = 0b01
    C2 = 0b10


class Reg_(IntEnum, shape=3): # type: ignore
    X8 = 0
    X9 = 1
    X10 = 2
    X11 = 3
    X12 = 4
    X13 = 5
    X14 = 6
    X15 = 7


class InsCR(Struct):
    op: Op
    rs2: Reg
    rdrs1: Reg
    funct4: unsigned(4)


class InsCI(Struct):
    op: Op
    imm: unsigned(5)
    rdrs1: Reg
    imm2: unsigned(1)
    funct3: unsigned(3)


class InsCSS(Struct):
    op: Op
    rs2: Reg
    imm: unsigned(6)
    funct3: unsigned(3)


class InsCIW(Struct):
    op: Op
    rd_: Reg_
    imm: unsigned(8)
    funct3: unsigned(3)


class InsCL(Struct):
    op: Op
    rd_: Reg_
    imm: unsigned(2)
    rs1_: Reg_
    imm2: unsigned(3)
    funct3: unsigned(3)


class InsCS(Struct):
    op: Op
    rs2_: Reg_
    imm: unsigned(2)
    rs1_: Reg_
    imm2: unsigned(3)
    funct3: unsigned(3)


class InsCA(Struct):
    op: Op
    rs2_: Reg_
    funct2: unsigned(2)
    rd_rs1_: Reg_
    funct6: unsigned(6)


class InsCB(Struct):
    op: Op
    offset: unsigned(5)
    rs1_: Reg_
    offset2: unsigned(3)
    funct3: unsigned(3)


class InsCJ(Struct):
    op: Op
    jump_target: unsigned(11)
    funct3: unsigned(3)
