from amaranth import unsigned, Signal, Const
from amaranth.lib.data import Struct
from amaranth.lib.enum import Enum

__all__ = ["Reg", "Opcode", "OpImmFunct", "InsI", "InsIS"]


class Reg(Enum, shape=5):
    X0 = 0
    X1 = 1
    X2 = 2
    X3 = 3
    X4 = 4
    X5 = 5
    # ...
    X30 = 30
    X31 = 31


class Opcode(Enum, shape=7):
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


class OpImmFunct(Enum, shape=3):
    ADDI = 0b000
    SLTI = 0b010
    SLTIU = 0b011
    XORI = 0b100
    ORI = 0b110
    ANDI = 0b111


# R:
#   31-25: funct7
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode


# I:
#   31-20: imm[11:0]
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
class InsIS(Struct):
    opcode: Opcode
    rd: Reg
    funct: OpImmFunct
    rs1: Reg
    imm: unsigned(12)


def InsI(opcode, funct, rs1, rd, imm):
    return InsIS.const(locals()).as_value().value


# S:
#   31-25: imm[11:5]
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-7: imm[4:0]
#     6-0: opcode


# B:
#      31: imm[12]
#   30-25: imm[10:5]
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-8: imm[4:1]
#       7: imm[11]
#     6-0: opcode


# U:
#   31-12: imm[31:12]
#    11-7: rd
#     6-0: opcode


# J:
#      31: imm[20]
#   30-21: imm[10:1]
#      20: imm[11]
#   19-12: imm[19:12]
#    11-7: rd
#     6-0: opcode
