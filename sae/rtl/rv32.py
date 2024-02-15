from functools import partial

from amaranth import unsigned
from amaranth.lib.data import Struct
from amaranth.lib.enum import Enum, IntEnum

__all__ = [
    "INSNS",
    "Reg",
    "Opcode",
    "OpImmFunct",
    "OpBranchFunct",
    "OpRegFunct",
    "OpLoadFunct",
    "OpStoreFunct",
    "InsI",
    "InsU",
    "InsR",
    "InsJ",
    "InsS",
    "InsB",
]

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
    ADDSUB = 0b000
    SLT = 0b010
    SLTU = 0b011
    AND = 0b111
    OR = 0b110
    XOR = 0b100
    SLL = 0b001
    SR = 0b101


class OpBranchFunct(IntEnum, shape=3):
    BEQ = 0b000
    BNE = 0b001
    BLT = 0b100
    BGE = 0b101
    BLTU = 0b110
    BGEU = 0b111


class OpLoadFunct(IntEnum, shape=3):
    LB = 0b000
    LH = 0b001
    LW = 0b010
    LBU = 0b100
    LHU = 0b101


class OpStoreFunct(IntEnum, shape=3):
    SB = 0b000
    SH = 0b001
    SW = 0b010


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
        funct3, funct7 = {
            "add": ("ADDSUB", 0),
            "srl": ("SR", 0),
            "sub": ("ADDSUB", 0b0100000),
            "sra": ("SR", 0b0100000),
        }.get(op, (op.upper(), 0))
        return value(
            InsR,
            opcode=Opcode.OP,
            funct3=OpRegFunct[funct3],
            rs1=rs1,
            rs2=rs2,
            rd=rd,
            funct7=funct7,
        )

    add_insn(op, f)

add_insn("snez", lambda op, rd, rs: Sltu(rd, Reg.X0, rs))


# I:
#   31-20: imm[11:0]
#   19-15: rs1
#   14-12: funct3
#    11-7: rd
#     6-0: opcode
class InsI(Struct):
    opcode: Opcode
    rd: Reg
    funct3: OpImmFunct
    rs1: Reg
    imm: unsigned(12)


# TODO: bounds checking on imm arguments

for op in ["addi", "slti", "sltiu", "andi", "ori", "xori", "jalr", "load"]:

    def f(op, rd, rs1, imm):
        if imm > 0:
            assert 0 < imm <= 2**12 - 1, f"imm is {imm}"
        elif imm < 0:
            assert 0 < -imm <= 2**12 - 1, f"imm is {imm}"  # XXX check

        match op:
            case "jalr":
                opcode = Opcode.JALR
                funct3 = 0
            case _:
                opcode = Opcode.OP_IMM
                funct3 = OpImmFunct[op.upper()]
        return value(InsI, opcode=opcode, funct3=funct3, rs1=rs1, rd=rd, imm=imm)

    add_insn(op, f)

for op in ["lw", "lh", "lhu", "lb", "lbu"]:

    def f(op, rd, rs1, imm):
        return value(
            InsI,
            opcode=Opcode.LOAD,
            rd=rd,
            funct3=OpLoadFunct[op.upper()],
            rs1=rs1,
            imm=imm,
        )

    add_insn(op, f)


def li(op, rd, imm):
    if (imm & 0xFFF) == imm:
        return Addi(rd, Reg.X0, imm)
    if imm & 0x800:
        return [
            Lui(rd, imm >> 12),
            Addi(rd, rd, (imm & 0xFFF) >> 1),
            Addi(rd, rd, ((imm & 0xFFF) >> 1) + int(imm & 1)),
        ]
    return [
        Lui(rd, imm >> 12),
        Addi(rd, rd, imm & 0xFFF),
    ]


add_insn("li", li)

add_insn("mv", lambda op, rd, rs: Addi(rd, rs, 0))
add_insn("seqz", lambda op, rd, rs: Sltiu(rd, rs, 1))
add_insn("not", lambda op, rd, rs: Xori(rd, rs, -1))
add_insn("nop", lambda op: Addi(Reg.X0, Reg.X0, 0))

for op in ["slli", "srli", "srai"]:

    def f(op, rd, rs1, shamt):
        assert 0 <= shamt <= 0b11111, f"shamt is {shamt}"

        funct3, imm11_5 = {
            "srli": ("SRI", 0b0000000),
            "srai": ("SRI", 0b0100000),
        }.get(op, (op.upper(), 0))
        return value(
            InsI,
            opcode=Opcode.OP_IMM,
            funct3=OpImmFunct[funct3],
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
class InsS(Struct):
    opcode: Opcode
    imm4_0: unsigned(5)
    funct3: unsigned(3)
    rs1: Reg
    rs2: Reg
    imm11_5: unsigned(7)


for op in ["sw", "sh", "sb"]:

    def f(op, rs1, rs2, imm):
        return value(
            InsS,
            opcode=Opcode.STORE,
            imm4_0=imm & 0x1F,
            funct3=OpStoreFunct[op.upper()],
            rs1=rs1,
            rs2=rs2,
            imm11_5=(imm >> 5),
        )

    add_insn(op, f)


# B:
#      31: imm[12]
#   30-25: imm[10:5]
#   24-20: rs2
#   19-15: rs1
#   14-12: funct3
#    11-8: imm[4:1]
#       7: imm[11]
#     6-0: opcode
class InsB(Struct):
    opcode: Opcode
    imm11: unsigned(1)
    imm4_1: unsigned(4)
    funct3: OpBranchFunct
    rs1: Reg
    rs2: Reg
    imm10_5: unsigned(6)
    imm12: unsigned(1)


for op in ["beq", "bne", "blt", "bge", "bltu", "bgeu"]:

    def f(op, rs1, rs2, imm):
        assert not (imm & 0b1)
        return value(
            InsB,
            opcode=Opcode.BRANCH,
            imm11=(imm >> 11) & 0b1,
            imm4_1=(imm >> 1) & 0xF,
            funct3=OpBranchFunct[op.upper()],
            rs1=rs1,
            rs2=rs2,
            imm10_5=(imm >> 5) & 0x3FF,
            imm12=(imm >> 12) & 0b1,
        )

    add_insn(op, f)


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
#
class InsJ(Struct):
    opcode: Opcode
    rd: Reg
    imm19_12: unsigned(8)
    imm11: unsigned(1)
    imm10_1: unsigned(10)
    imm20: unsigned(1)


def jal(op, rd, imm):
    assert not (imm & 0b1)
    return value(
        InsJ,
        opcode=Opcode.JAL,
        rd=rd,
        imm19_12=(imm >> 12) & 0xFF,
        imm11=(imm >> 11) & 0b1,
        imm10_1=(imm >> 1) & 0x3FF,
        imm20=imm >> 20,
    )


add_insn("jal", jal)
add_insn("j", lambda op, imm: Jal(Reg.X0, imm))
