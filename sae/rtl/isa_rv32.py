from __future__ import annotations

import re

from amaranth import unsigned
from amaranth.lib.enum import IntEnum

from .. import st
from ..isa import ISA, ILayout, ITransform, RegisterSpecifier, fn_insn

__all__ = ["RV32I", "RV32IC"]

_immsingle = re.compile(r"\Aimm(\d+)\Z")
_immmulti = re.compile(r"\Aimm(\d+)_(\d+)\Z")


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

    Reg = RegisterSpecifier(
        5,
        [("zero", "x0"),
         ("ra", "x1"), ("sp", "x2"), ("gp", "x3"), ("tp", "x4"),
         ("t0", "x5"), ("t1", "x6"), ("t2", "x7"),
         ("fp", "s0", "x8"), ("s1", "x9"),
         ("a0", "x10"), ("a1", "x11"), ("a2", "x12"), ("a3", "x13"),
         ("a4", "x14"), ("a5", "x15"), ("a6", "x16"), ("a7", "x17"),
         ("s2", "x18"), ("s3", "x19"), ("s4", "x20"), ("s5", "x21"),
         ("s6", "x22"), ("s7", "x23"), ("s8", "x24"), ("s9", "x25"),
         ("s10", "x26"), ("s11", "x27"),
         ("t3", "x28"), ("t4", "x29"), ("t5", "x30"), ("t6", "x31")])


    class ImmXfrm(ITransform):
        def __init__(self, ilcls):
            self._singles = {}
            self._ranges = {}

            layout = []
            for n in ilcls.layout:
                if m := _immsingle.match(n):
                    layout.append(n)
                    self._singles[n] = int(m[1])
                elif m := _immmulti.match(n):
                    layout.append(n)
                    self._ranges[n] = (int(m[1]), int(m[2]))

            super().__init__(ilcls, inputs=["imm"], layout=layout)

        def inputs_to_layout(self, *, imm):
            layout = {}
            for elem, off in self._singles.items():
                layout[elem] = (imm >> off) & 1
            for elem, (top, bottom) in self._ranges.items():
                layout[elem] = (imm >> bottom) & (2 ** (top - bottom + 1) - 1)
            return layout

        def layout_to_inputs(self, **kwargs):
            imm = 0
            for elem, off in self._singles.items():
                imm += kwargs[elem] << off
            for elem, (_top, bottom) in self._ranges.items():
                imm += kwargs[elem] << bottom
            return {"imm": imm}


    class IL(ILayout, len=32):
        opcode: Opcode
        rd: Reg
        rs1: Reg
        rs2: Reg

        def resolve(
            name,
            *,
            after,
            remlen,
            functn=re.compile(r"\Afunct(\d+)\Z"),
        ):
            if m := functn.match(name):
                return unsigned(int(m[1]))
            if name == "imm":
                assert not after, "don't know how to deal with non-last imm"
                return unsigned(remlen)
            if m := _immmulti.match(name):
                top = int(m[1])
                bottom = int(m[2])
                assert top > bottom, "immY_X format maps to imm[Y:X], Y must be > X"
                return unsigned(top - bottom + 1)
            if m := _immsingle.match(name):
                return unsigned(1)
            assert False, f"unhandled: {name!r}"


    class R(IL):
        layout = ("opcode", "rd", "funct3", "rs1", "rs2", "funct7")
        defaults = {"opcode": "OP", "funct7": 0}

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
    SUB = ADD(funct7=R.F7Negate)
    SRA = SRL(funct7=R.F7Negate)

    SNEZ = SLTU(rs1="zero")

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

        class MMFunct(IntEnum, shape=3):
            FENCE = 0b000

        class SFunct(IntEnum, shape=15):
            ECALL = 0b000000000000000
            EBREAK = 0b000000000001000

    class ShamtXfrm(ITransform):
        def __init__(self, ilcls, *, imm11_5=0):
            super().__init__(ilcls, inputs=["shamt"], layout=["imm"])
            self.imm11_5 = imm11_5

        def inputs_to_layout(self, *, shamt):
            assert 0 <= shamt < 2**5, f"shamt is {shamt!r}"
            return {"imm": (self.imm11_5 << 5) | shamt}

        def layout_to_inputs(self, *, imm):
            return {"shamt": imm}

    ADDI = I(funct3=I.IFunct.ADDI)
    SLTI = I(funct3=I.IFunct.SLTI)
    SLTIU = I(funct3=I.IFunct.SLTIU)
    XORI = I(funct3=I.IFunct.XORI)
    ORI = I(funct3=I.IFunct.ORI)
    ANDI = I(funct3=I.IFunct.ANDI)

    SLLI = I(funct3=I.IFunct.SLLI).xfrm(ShamtXfrm)
    SRLI = I(funct3=I.IFunct.SRI).xfrm(ShamtXfrm)
    SRAI = I(funct3=I.IFunct.SRI).xfrm(ShamtXfrm, imm11_5=0b0100000)

    JALR = I(opcode="JALR", funct3=0)
    RET = JALR(rd="zero", rs1="ra", imm=0)

    class RS1OffXfrm(ITransform):
        def __init__(self, ilcls):
            super().__init__(ilcls, inputs=["rs1off"], layout=["imm", "rs1"])

        def inputs_to_layout(self, *, rs1off):
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

        def layout_to_inputs(self, *, imm, rs1):
            return {"rs1off": (imm, rs1)}

    _load = I(opcode="LOAD").xfrm(RS1OffXfrm)
    LB = _load(funct3=I.LFunct.LB)
    LH = _load(funct3=I.LFunct.LH)
    LW = _load(funct3=I.LFunct.LW)
    LBU = _load(funct3=I.LFunct.LBU)
    LHU = _load(funct3=I.LFunct.LHU)

    @staticmethod
    def fence_arg(a, *, _arg=re.compile(r"\A[rwio]+\Z")):
        a = a.lower()
        assert _arg.match(a) is not None
        return (
            (0b0001 if "w" in a else 0)
            | (0b0010 if "r" in a else 0)
            | (0b0100 if "o" in a else 0)
            | (0b1000 if "i" in a else 0))

    @staticmethod
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

    class FenceXfrm(ITransform):
        def __init__(self, ilcls, *, fm=0):
            super().__init__(ilcls, inputs=["pred", "succ"], layout=["imm"])
            self.fm = fm

        def inputs_to_layout(self, *, pred, succ):
            imm = RV32I.fence_arg(succ) | (RV32I.fence_arg(pred) << 4) | (self.fm << 8)
            return {"imm": imm}

        def layout_to_inputs(self, *, imm):
            if imm >> 8 != self.fm:
                return None
            return {
                "pred": RV32I.arg_fence((imm & 0xf0) >> 4),
                "succ": RV32I.arg_fence(imm & 0x0f),
            }

    _fence = I(opcode="MISC_MEM", funct3=I.MMFunct.FENCE, rd=0, rs1=0)
    FENCE = _fence.xfrm(FenceXfrm)
    FENCE_TSO = _fence.xfrm(FenceXfrm, fm=0b1000)(pred="rw", succ="rw")

    class SystemXfrm(ITransform):
        def __init__(self, ilcls):
            super().__init__(ilcls, inputs=["funct"], layout=["funct3", "imm"])

        def inputs_to_layout(self, *, funct):
            return {"funct3": funct & 0x7, "imm": funct >> 3}

    _system = I(opcode="SYSTEM", rd=0, rs1=0).xfrm(SystemXfrm)
    ECALL = _system(funct=I.SFunct.ECALL)
    EBREAK = _system(funct=I.SFunct.EBREAK)

    @fn_insn
    def LI(cls, *, rd, imm):
        if (imm & 0xFFF) == imm:
            return cls.ADDI.value(rd=rd, rs1="x0", imm=imm)
        if imm & 0x800:
            return [
                cls.LUI.value(rd=rd, imm=imm >> 12),
                cls.ADDI.value(rd=rd, rs1=rd, imm=(imm & 0xFFF) >> 1),
                cls.ADDI.value(rd=rd, rs1=rd, imm=((imm & 0xFFF) >> 1) + int(imm & 1)),
            ]
        return [
            cls.LUI.value(rd=rd, imm=imm >> 12),
            cls.ADDI.value(rd=rd, rs1=rd, imm=imm & 0xFFF),
        ]

    MV = ADDI(imm=0)
    SEQZ = SLTIU(imm=1)
    NOT = XORI(imm=-1)
    NOP = ADDI(rd="zero", rs1="zero", imm=0)

    class S(IL):
        layout = ("opcode", "imm4_0", "funct3", "rs1", "rs2", "imm11_5")
        defaults = {"opcode": "STORE"}

        class Funct(IntEnum, shape=3):
            SB = 0b000
            SH = 0b001
            SW = 0b010

    _store = S().xfrm(ImmXfrm).xfrm(RS1OffXfrm)
    SB = _store(funct3=S.Funct.SB)
    SH = _store(funct3=S.Funct.SH)
    SW = _store(funct3=S.Funct.SW)

    class B(IL):
        layout = (
            "opcode",
            "imm11",
            "imm4_1",
            "funct3",
            "rs1",
            "rs2",
            "imm10_5",
            "imm12")
        defaults = {"opcode": "BRANCH"}

        class Funct(IntEnum, shape=3):
            BEQ = 0b000
            BNE = 0b001
            BLT = 0b100
            BGE = 0b101
            BLTU = 0b110
            BGEU = 0b111

    _branch = B().xfrm(ImmXfrm)
    BEQ = _branch(funct3=B.Funct.BEQ)
    BNE = _branch(funct3=B.Funct.BNE)
    BLT = _branch(funct3=B.Funct.BLT)
    BGE = _branch(funct3=B.Funct.BGE)
    BLTU = _branch(funct3=B.Funct.BLTU)
    BGEU = _branch(funct3=B.Funct.BGEU)

    class U(IL):
        layout = ("opcode", "rd", "imm")

    class CheckXfrm(ITransform):
        def __init__(self, ilcls):
            super().__init__(ilcls, inputs=["imm"], layout=["imm"])

        def inputs_to_layout(self, *, imm):
            if imm > 0:
                assert 0 < imm <= 2**20 - 1, f"imm is {imm}"
            elif imm < 0:
                assert 0 < -imm <= 2**20 - 1, f"imm is {imm}"
            return {"imm": imm}

        def layout_to_inputs(self, *, imm):
            return {"imm": imm}

    _upper = U().xfrm(CheckXfrm)
    LUI = _upper(opcode="LUI")
    AUIPC = _upper(opcode="AUIPC")

    class J(IL):
        layout = ("opcode", "rd", "imm19_12", "imm11", "imm10_1", "imm20")
        defaults = {"opcode": "JAL"}

    JAL = J().xfrm(ImmXfrm)
    J_ = JAL(rd="zero")


class RV32IC(RV32I):
    class Op(IntEnum, shape=2):
        C0 = 0b00
        C1 = 0b01
        C2 = 0b10

    Reg_ = RegisterSpecifier(
        3,
        [("s0", "x8"),
         ("s1", "x9"),
         ("a0", "x10"),
         ("a1", "x11"),
         ("a2", "x12"),
         ("a3", "x13"),
         ("a4", "x14"),
         ("a5", "x15")])

    class IL(ILayout, len=16):
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
