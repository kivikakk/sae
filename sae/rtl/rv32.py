import re
from enum import Enum as PyEnum
from functools import partial

from amaranth import C, unsigned
from amaranth.lib.data import Struct
from amaranth.lib.enum import IntEnum

__all__ = [
    "ISA",
    "INSNS",
    "Reg",
    "Opcode",
    "OpImmFunct",
    "OpBranchFunct",
    "OpRegFunct",
    "OpLoadFunct",
    "OpStoreFunct",
    "OpMiscMemFunct",
    "OpSystemFunct",
    "InsI",
    "InsU",
    "InsR",
    "InsJ",
    "InsS",
    "InsB",
    "disasm",
]


class ISA(PyEnum):
    RVI = 1
    RVC = 2


INSNS = {}


def add_insn(op, f):
    global INSNS
    name = op[0].upper() + op[1:]
    f.__name__ = name
    f = partial(f, op)
    INSNS[name] = f


def value(struct, **kwargs):
    v = struct.const(kwargs).as_value().value
    return [
        v & 0x0000FFFF,
        (v >> 16) & 0xFFFF,
    ]


REG_MAPPINGS = [
    # x0-x4
    "zero",
    "ra",
    "sp",
    "gp",
    "tp",
    # x5-x7
    "t0",
    "t1",
    "t2",
    # x8-x9
    "fp",
    "s1",  # s0=fp
    # x10-x17
    "a0",
    "a1",
    "a2",
    "a3",
    "a4",
    "a5",
    "a6",
    "a7",
    # x18-x27
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "s8",
    "s9",
    "s10",
    "s11",
    # x28-x31
    "t3",
    "t4",
    "t5",
    "t6",
]


class Reg(IntEnum, shape=5):
    # X0..X31 = 0..31
    global i
    for i in range(32):
        locals()[f"X{i}"] = i

    @classmethod
    def _missing_(cls, value):
        try:
            ix = REG_MAPPINGS.index(value.lower())
        except ValueError:
            return cls[value]
        else:
            return cls[f"X{ix}"]


def reg_friendly(self):
    return REG_MAPPINGS[self]


Reg.friendly = property(reg_friendly)


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


class OpImmFunct(IntEnum, shape=3):
    ADDI = 0b000
    SLTI = 0b010
    SLTIU = 0b011
    XORI = 0b100
    ORI = 0b110
    ANDI = 0b111
    SLLI = 0b001
    SRI = 0b101


class OpRegFunct(IntEnum, shape=3):
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
    # Note the bottom 2 bits convey the size the same as AccessWidth.
    LB = 0b000
    LH = 0b001
    LW = 0b010
    LBU = 0b100
    LHU = 0b101


class OpStoreFunct(IntEnum, shape=3):
    SB = 0b000
    SH = 0b001
    SW = 0b010


class OpMiscMemFunct(IntEnum, shape=3):
    FENCE = 0b000


class OpSystemFunct(IntEnum, shape=15):
    ECALL = 0b000000000000000
    EBREAK = 0b000000000001000


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

add_insn("snez", lambda op, rd, rs: INSNS["Sltu"](rd, Reg.X0, rs))


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


def hoff(offset):
    """Take an Offset or a (offset, reg) pair, spit out the latter."""
    if isinstance(offset, tuple):
        return offset
    return (offset.offset, Reg[offset.register.register.upper()])


for op in ["lw", "lh", "lhu", "lb", "lbu"]:

    def f(op, rd, rs1off):
        (imm, rs1) = hoff(rs1off)
        return value(
            InsI,
            opcode=Opcode.LOAD,
            rd=rd,
            funct3=OpLoadFunct[op.upper()],
            rs1=rs1,
            imm=imm,
        )

    add_insn(op, f)

FENCE_ARG = re.compile(r"\A[rwio]+\Z")


def fence_arg(a):
    a = a.lower()
    assert FENCE_ARG.match(a) is not None
    return (
        (0b0001 if "w" in a else 0)
        | (0b0010 if "r" in a else 0)
        | (0b0100 if "o" in a else 0)
        | (0b1000 if "i" in a else 0)
    )


def arg_fence(v):
    assert not (v & ~0b1111)
    a = []
    if v & 0b1000:
        a.append("i")
    if v & 0b0100:
        a.append("o")
    if v & 0b0010:
        a.append("r")
    if v & 0b0001:
        a.append("w")
    return "".join(a)


def fence(op, pred, succ, *, fm=0):
    return value(
        InsI,
        opcode=Opcode.MISC_MEM,
        rd=0,
        funct3=OpMiscMemFunct.FENCE,
        rs1=0,
        imm=fence_arg(succ) | (fence_arg(pred) << 4) | (fm << 8),
    )


add_insn("fence", fence)
add_insn("fence.tso", lambda op: fence(op, "rw", "rw", fm=0b1000))


for op in ["ecall", "ebreak"]:

    def f(op):
        funct = OpSystemFunct[op.upper()]
        return value(
            InsI, opcode=Opcode.SYSTEM, rd=0, funct3=funct & 0x7, rs1=0, imm=funct >> 3
        )

    add_insn(op, f)


def li(op, rd, imm):
    if (imm & 0xFFF) == imm:
        return INSNS["Addi"](rd, Reg.X0, imm)
    if imm & 0x800:
        return [
            *INSNS["Lui"](rd, imm >> 12),
            *INSNS["Addi"](rd, rd, (imm & 0xFFF) >> 1),
            *INSNS["Addi"](rd, rd, ((imm & 0xFFF) >> 1) + int(imm & 1)),
        ]
    return [
        *INSNS["Lui"](rd, imm >> 12),
        *INSNS["Addi"](rd, rd, imm & 0xFFF),
    ]


add_insn("li", li)

add_insn("mv", lambda op, rd, rs: INSNS["Addi"](rd, rs, 0))
add_insn("seqz", lambda op, rd, rs: INSNS["Sltiu"](rd, rs, 1))
add_insn("not", lambda op, rd, rs: INSNS["Xori"](rd, rs, -1))
add_insn("nop", lambda op: INSNS["Addi"](Reg.X0, Reg.X0, 0))

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

    def f(op, rs2, rs1off):
        (imm, rs1) = hoff(rs1off)
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
        assert not (imm & 1)
        return value(
            InsB,
            opcode=Opcode.BRANCH,
            imm11=(imm >> 11) & 1,
            imm4_1=(imm >> 1) & 0xF,
            funct3=OpBranchFunct[op.upper()],
            rs1=rs1,
            rs2=rs2,
            imm10_5=(imm >> 5) & 0x3FF,
            imm12=(imm >> 12) & 1,
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
    assert not (imm & 1)
    return value(
        InsJ,
        opcode=Opcode.JAL,
        rd=rd,
        imm19_12=(imm >> 12) & 0xFF,
        imm11=(imm >> 11) & 1,
        imm10_1=(imm >> 1) & 0x3FF,
        imm20=imm >> 20,
    )


add_insn("jal", jal)
add_insn("j", lambda op, imm: INSNS["Jal"](Reg.X0, imm))


def decode(struct, value):
    view = struct(C(value, 32))
    result = {}
    for field in struct._AggregateMeta__layout._fields:
        slice = view[field]
        assert type(slice).__name__ == "Slice"
        v = (slice.value.value & (2**slice.stop - 1)) >> slice.start
        result[field] = v
    return result


def c2(count, value):
    sb = 1 << (count - 1)
    if value & sb:
        return -((sb << 1) - value)
    return value


def c2foff(count, value):
    v = c2(count, value)
    if v == 0:
        return "0"
    elif v < 0:
        return f"-0x{-v:x}"
    else:
        return f"0x{v:x}"


def disasm(op):
    v_i = decode(InsI, op)
    v_b = decode(InsB, op)
    v_u = decode(InsU, op)
    v_r = decode(InsR, op)
    v_j = decode(InsJ, op)
    v_s = decode(InsS, op)

    try:
        opcode = Opcode(v_i["opcode"])
    except ValueError:
        opcode = v_i["opcode"]

    match opcode:
        case Opcode.LOAD:
            return f"{OpLoadFunct(v_i['funct3']).name.lower()} x{v_i['rd']}, {c2foff(12, v_i['imm'])}(x{v_i['rs1']})"
        case Opcode.MISC_MEM:
            match v_i["funct3"]:
                case OpMiscMemFunct.FENCE:
                    succ = v_i["imm"] & 0xF
                    pred = (v_i["imm"] >> 4) & 0xF
                    fm = v_i["imm"] >> 8
                    if fm == 0b1000 and succ == pred == 0b0011:
                        return "fence.tso"
                    return f"fence {arg_fence(pred)}, {arg_fence(succ)}"
        case Opcode.OP_IMM:
            funct = OpImmFunct(v_i["funct3"])
            if funct == OpImmFunct.ADDI and v_i["imm"] == 0:
                if v_i["rd"] == v_i["rs1"] == 0:
                    return "nop"
                return f"mv x{v_i['rd']}, x{v_i['rs1']}"
            if funct == OpImmFunct.ADDI and v_i["rs1"] == 0:
                return f"li x{v_i['rd']}, 0x{v_i['imm']:x}"
            if funct == OpImmFunct.SLTIU and v_i["imm"] == 1:
                return f"seqz x{v_i['rd']}, x{v_i['rs1']}"
            if funct == OpImmFunct.XORI and v_i["imm"] == 0xFFF:
                return f"not x{v_i['rd']}, x{v_i['rs1']}"
            match funct:
                case OpImmFunct.ADDI | OpImmFunct.SLTI:
                    return f"{funct.name.lower()} x{v_i['rd']}, x{v_i['rs1']}, {c2foff(12, v_i['imm'])}"
                case (
                    OpImmFunct.SLTIU
                    | OpImmFunct.ANDI
                    | OpImmFunct.ORI
                    | OpImmFunct.XORI
                    | OpImmFunct.SLLI
                ):
                    return f"{funct.name.lower()} x{v_i['rd']}, x{v_i['rs1']}, 0x{v_i['imm']:x}"
                case OpImmFunct.SRI:
                    opc = "srai" if (v_i["imm"] >> 10) & 1 else "srli"
                    return f"{opc} x{v_i['rd']}, x{v_i['rs1']}, 0x{v_i['imm'] & 0b111111:x}"
        case Opcode.OP:
            funct = OpRegFunct(v_r["funct3"])
            if funct == OpRegFunct.SLTU and v_r["rs1"] == 0:
                return f"snez x{v_r['rd']}, x{v_r['rs2']}"
            match funct:
                case OpRegFunct.ADDSUB:
                    opc = "sub" if (v_r["funct7"] >> 5) & 1 else "add"
                    return f"{opc} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
                case (
                    OpRegFunct.SLT
                    | OpRegFunct.SLTU
                    | OpRegFunct.AND
                    | OpRegFunct.OR
                    | OpRegFunct.XOR
                    | OpRegFunct.SLL
                ):
                    return f"{funct.name.lower()} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
                case OpRegFunct.SR:
                    opc = "sra" if (v_r["funct7"] >> 5) & 1 else "srl"
                    return f"{opc} x{v_r['rd']}, x{v_r['rs1']}, x{v_r['rs2']}"
        case Opcode.LUI | Opcode.AUIPC:
            return f"{opcode.name.lower()} x{v_u['rd']}, 0x{v_u['imm']:x}"
        case Opcode.STORE:
            imm = v_s["imm4_0"] | v_s["imm11_5"] << 5
            return f"{OpStoreFunct(v_s['funct3']).name.lower()} x{v_s['rs2']}, {c2foff(12, imm)}(x{v_s['rs1']})"
        case Opcode.BRANCH:
            imm = (
                v_b["imm4_1"] << 1
                | v_b["imm10_5"] << 5
                | v_b["imm11"] << 11
                | v_b["imm12"] << 12
            )
            return f"{OpBranchFunct(v_b['funct3']).name.lower()} x{v_b['rs1']}, x{v_b['rs2']}, {c2foff(13, imm)}"
        case Opcode.JALR:
            return f"jalr x{v_i['rd']}, x{v_i['rs1']}, {c2foff(12, v_i['imm'])}"
        case Opcode.JAL:
            imm = (
                v_j["imm10_1"] << 1
                | v_j["imm11"] << 11
                | v_j["imm19_12"] << 12
                | v_j["imm20"] << 20
            )
            if v_j["rd"] == 0:
                return f"j {c2foff(21, imm)}"
            return f"jal x{v_j['rd']}, {c2foff(21, imm)}"
        case Opcode.SYSTEM:
            if v_i["funct3"] == 0:
                funct = OpSystemFunct(v_i["imm"] << 3)
                return funct.name.lower()
        case 0x00:
            if op & 0xFFFF == 0:
                return "invalid"
        case 0x7F:
            if op == 0xFFFFFFFF:
                return "invalid"
    raise RuntimeError(f"unknown insn: {op:0>8x}")
