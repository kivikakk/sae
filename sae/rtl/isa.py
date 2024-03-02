from __future__ import annotations

import inspect
import re

from amaranth import Shape, unsigned
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import IntEnum, nonmember

from .rv32 import Opcode, Reg

"""

What is an ISA?

It encompasses:

* Instruction layouts.
  * Each layout has a common field, the opcode.
* Instructions encoded using those layouts.

"""


"""

TODO

* We could also use __init_subclass__ to bind registers to the ISA they were
  created in!

"""


class ISA:
    def __init_subclass__(cls):
        for name, obj in cls.__dict__.items():
            if getattr(obj, "_needs_renamed", False):
                del obj._needs_renamed
                obj.__name__ = name
            if getattr(obj, "_needs_finalised", False):
                obj.finalise(cls)

    @staticmethod
    def RegisterSpecifier(size, names):
        count = 2**size
        if len(names) < count:
            raise ValueError(
                f"Register naming is inadequate (named {len(names)}/{count})."
            )
        elif len(names) > count:
            raise ValueError(
                f"Register naming is excessive (named {len(names)}/{count})."
            )

        members = {}
        mappings = {}
        aliases_ = {}
        for i, ax in enumerate(names):
            match ax:
                case [primary, *rest]:
                    members[primary.upper()] = i
                    for a in rest:
                        mappings[a.upper()] = primary.upper()
                    aliases_[primary.upper()] = [n.upper() for n in ax]
                case str():
                    members[ax.upper()] = i
                case _:
                    raise TypeError(f"Unknown name specifier {ax!r}.")

        class Register(IntEnum, shape=size):
            locals().update(members)

            _mappings = nonmember(mappings)
            _aliases = nonmember(aliases_)
            _needs_renamed = nonmember(True)

            @classmethod
            def _missing_(cls, value):
                value = value.upper()
                try:
                    return cls[cls._mappings[value]]
                except KeyError:
                    return cls[value]

            @nonmember
            @property
            def aliases(self):
                return self._aliases[self._name_]

        return Register

    class ILayouts:
        _needs_finalised = True

        def __init_subclass__(cls, *, len):
            cls.len = len

        @classmethod
        def finalise(cls, isa):
            annotations = inspect.get_annotations(
                cls, locals=isa.__dict__, eval_str=True
            )
            for name, elems in cls.__dict__.items():
                if name[0] == name[0].lower():
                    continue
                if isinstance(elems, str):
                    # X = ("a") # oops!
                    elems = (elems,)
                il = ISA.ILayout(name, annotations, cls)
                for elem in elems:
                    il.append(elem)
                setattr(cls, name, il.finalise())

    class ILayout:
        def __init__(self, name, annotations, ils):
            self.name = name
            self.annotations = annotations
            self.len = ils.len

            self.after = None
            self.remlen = None

            self._ils = ils
            self._elems = []

        def append(self, name):
            self._elems.append(name)

        def finalise(self):
            self.fields = {}
            consumed = 0
            for i, elem in enumerate(self._elems):
                if not isinstance(elem, str):
                    raise TypeError(f"Unknown field specifier {elem!r}.")
                elif ty := self.annotations.get(elem, None):
                    self.fields[elem] = ty
                elif hasattr(self._ils, "resolve"):
                    self.after = self._elems[i + 1 :]
                    self.remlen = self.len - consumed
                    self.fields[elem] = self._ils.resolve(self, elem)
                else:
                    raise ValueError(
                        f"Field specifier {elem!r} not registered, and no default type "
                        f"function given."
                    )

                consumed += Shape.cast(self.fields[elem]).width

            if consumed < self.len:
                raise ValueError(
                    f"Layout components are inadequate (fills {consumed}/{self.len})."
                )
            elif consumed > self.len:
                raise ValueError(
                    f"Layout components are excessive (fills {consumed}/{self.len})."
                )

            IL = StructLayout(self.fields)
            IL.__name__ = self.name
            return IL


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
