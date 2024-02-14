from functools import partial

from amaranth import unsigned
from amaranth.lib.data import Struct
from amaranth.lib.enum import Enum, IntEnum

__all__ = ["INSNS", "Reg", "Opcode", "OpImmFunct", "OpRegFunct", "InsI", "InsU", "InsR"]

INSNS = {}


def add_insn(op, f):
    global INSNS, __all__
    name = op[0].upper() + op[1:]
    f.__name__ = name
    f = partial(f, op)
    INSNS[name] = f
    globals()[name] = f
    __all__.append(f)


def value(struct, **kwargs):
    return struct.const(kwargs).as_value().value


class Reg(IntEnum, shape=5):
    # X0..X31 = 0..31
    global i
    for i in range(32):
        locals()[f"X{i}"] = i


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
    SLLI = 0b001
    SRI = 0b101


class OpRegFunct(IntEnum, shape=10):
    ADD = 0b000
    SLT = 0b010
    SLTU = 0b011
    AND = 0b111
    OR = 0b110
    XOR = 0b100
    SLL = 0b001
    SRL = 0b101
    SUB = 0b0100000000
    SRA = 0b0100000101


# R:
#   31-25: funct7
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
class InsR(Struct):
    opcode: Opcode
    rd: Reg
    funct3: unsigned(3)
    rs1: Reg
    rs2: Reg
    funct7: unsigned(7)


for op in ["add", "slt", "sltu", "and", "or", "xor", "sll", "srl", "sub", "sra"]:

    def f(op, rd, rs1, rs2):
        funct = OpRegFunct[op.upper()]
        return value(
            InsR,
            opcode=Opcode.OP,
            funct3=funct & 0x7,
            rs1=rs1,
            rs2=rs2,
            rd=rd,
            funct7=funct >> 3,
        )

    add_insn(op, f)


# I:
#   31-20: imm[11:0]
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
class InsI(Struct):
    opcode: Opcode
    rd: Reg
    funct: OpImmFunct
    rs1: Reg
    imm: unsigned(12)


# TODO: bounds checking on imm arguments

for op in ["addi", "slti", "sltiu", "andi", "ori", "xori"]:

    def f(op, rd, rs1, imm):
        if imm > 0:
            assert 0 < imm <= 2**12 - 1, f"imm is {imm}"
        elif imm < 0:
            assert 0 < -imm <= 2**12 - 1, f"imm is {imm}"  # XXX check

        return value(
            InsI,
            opcode=Opcode.OP_IMM,
            funct=OpImmFunct[op.upper()],
            rs1=rs1,
            rd=rd,
            imm=imm,
        )

    add_insn(op, f)

for op in ["slli", "srli", "srai"]:

    def f(op, rd, rs1, shamt):
        assert 0 <= shamt <= 0b11111, f"shamt is {shamt}"

        funct, imm11_5 = {
            "slli": ("SLLI", 0),
            "srli": ("SRI", 0b0000000),
            "srai": ("SRI", 0b0100000),
        }[op]
        return value(
            InsI,
            opcode=Opcode.OP_IMM,
            funct=OpImmFunct[funct],
            rs1=rs1,
            rd=rd,
            imm=(imm11_5 << 5) | shamt,
        )

    add_insn(op, f)


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
class InsU(Struct):
    opcode: Opcode
    rd: Reg
    imm: unsigned(20)


for op in ["lui", "auipc"]:

    def f(op, rd, imm):
        if imm > 0:
            assert 0 < imm <= 2**20 - 1, f"imm is {imm}"
        elif imm < 0:
            assert (
                0 < -imm <= 2**20 - 1
            ), f"imm is {imm}"  # XXX check as above; boundary conditions etc.

        return value(InsU, opcode=Opcode[op.upper()], rd=rd, imm=imm)

    add_insn(op, f)


# J:
#      31: imm[20]
#   30-21: imm[10:1]
#      20: imm[11]
#   19-12: imm[19:12]
#    11-7: rd
#     6-0: opcode
