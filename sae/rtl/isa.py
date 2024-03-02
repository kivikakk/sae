import re
from contextlib import contextmanager

from amaranth import unsigned
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import IntEnum, nonmember

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

    @staticmethod
    def RegisterSpecifier(size, names):
        if len(names) < 2**size:
            raise ValueError("Register naming isn't exhaustive.")
        elif len(names) > 2**size:
            raise ValueError("Register naming is excessive.")

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

    @classmethod
    @contextmanager
    def ILayouts(cls):
        yield cls.ILayoutHelper()

    class ILayoutHelper:
        _unset = object()

        def __init__(self):
            self._registered = {}
            self._default_len = None
            self._default_type_fn = None

        def register(self, **kwargs):
            self._registered.update(kwargs)

        def default(self, *, len=_unset, type_fn=_unset):
            if len is not self._unset:
                self._default_len = len
            if type_fn is not self._unset:
                self._default_type_fn = type_fn

        def __call__(self, *args):
            args = list(args)
            len = args.pop(0) if isinstance(args[0], int) else self._default_len
            if len is None:
                raise ValueError("ILayout needs a len, and no default is set.")

            fields = {}
            for arg in args:
                if not isinstance(arg, str):
                    raise TypeError(f"Unknown field specifier {arg!r}.")
                if ty := self._registered.get(arg):
                    fields[arg] = ty
                elif self._default_type_fn is not None:
                    fields[arg] = self._default_type_fn(arg)
                else:
                    raise ValueError(
                        f"Field specifier {arg!r} not registered, and no default type "
                        f"function given."
                    )

            IL = StructLayout(fields)
            IL._needs_renamed = nonmember(True)

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

    with ISA.ILayouts() as il:
        il.register(opcode=Opcode, rd=Reg, rs1=Reg, rs2=Reg)

        def type_fn(m, *, functn=re.compile(r"\Afunct(\d+)\Z")):
            return unsigned(int(functn.match(m)[1]))

        il.default(len=32, type_fn=type_fn)

        R = il("opcode", "rd", "funct3", "rs1", "rs2", "funct7")
        I = il("opcode", "rd", "funct3", "rs1", "imm")  # imm = 12
        S = il("opcode", "imm4_0", "funct3", "rs1", "rs2", "imm11_5")
        B = il("opcode", "imm11", "imm4_1", "funct3", "rs1", "rs2", "imm10_5", "imm12")
        U = il("opcode", "rd", "imm")
        J = il("opcode", "rd", "imm19_12", "imm11", "imm10_1", "imm20")
