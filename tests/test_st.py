import inspect
import re
import unittest
from contextlib import contextmanager
from functools import singledispatch
from pathlib import Path
from typing import Any, Optional

from amaranth.lib.memory import Memory

from sae import st
from sae.rtl.hart import FaultCode, Hart
from sae.rtl.isa_rv32 import RV32I

from .test_utils import run_until_fault

Reg = RV32I.Reg


class StError(RuntimeError):
    filename: str
    lineno: Optional[int]
    line: str

    def __init__(self, filename, lineno, line):
        self.filename = filename
        self.lineno = lineno
        self.line = line

    def __str__(self):
        return f"{self.filename}:{self.lineno}: {self.line}"


@contextmanager
def annotate_exceptions(filename, line):
    try:
        yield
    except Exception as e:
        raise StError(filename, line.lineno, line.line) from e


def parse_pairs(args, *, allow_atoms=False):
    pairs = {}
    rest = []
    for arg in args:
        if isinstance(arg, str):
            rest.append(arg)
        elif isinstance(arg.register, str):
            pairs[arg.register] = arg.assign
        else:
            pairs[Reg(arg.register.register.upper())] = arg.assign
    if allow_atoms:
        return pairs, rest
    assert not rest, "unpaired arguments but allow_atoms=False"
    return pairs


@singledispatch
def translate_arg(arg, name):
    if isinstance(arg, st.Register):
        return Reg(arg.register.upper())
    elif isinstance(arg, (int, st.Offset)):
        return arg
    elif name in ("pred", "succ"):
        return arg
    assert False, f"arg weh {name!r} = {arg!r}"


@translate_arg.register(list)
def translate_arg_list(args, names):
    return {name: translate_arg(arg, name) for arg, name in zip(args, names)}


class UnwrittenClass:
    def __repr__(self):
        return "Unwritten"


Unwritten = UnwrittenClass()


class StTestCase(unittest.TestCase):
    _reg_inits: dict[str | Reg, Any]
    _body: list[int]
    _rest_unwritten: bool = False
    _results: dict[str | Reg, Any]
    _asserted: set[str | Reg]

    def __init_subclass__(cls):
        super().__init_subclass__()

        parser = st.Parser()
        with open(Path(__file__).parent / cls.filename, "r") as f:
            parser.feed(f.readlines())

        for name, body in parser.results:
            assert name.startswith("test_"), f"what do i do with {name!r}?"
            setattr(cls, name, lambda self, body=body: cls.st_runner(self, body))

    def init_st(self, args, *, body=None):
        self.fish_st()

        self._reg_inits, rest = parse_pairs(args, allow_atoms=True)
        assert not rest, "remaining init args"
        self._body = body or []
        self._rest_unwritten = True
        self._results = None

    def st_runner(self, body):
        for line in body:
            with annotate_exceptions(self.filename, line):
                match line:
                    case st.Pragma(kind="init", args=args):
                        self.init_st(args)
                    case st.Op(opcode=opcode, args=args):
                        opname = opcode.upper().replace(".", "_")
                        if len(opname) == 1:
                            opname += "_"
                        insn = getattr(RV32I, opname)
                        if hasattr(insn, "asm_args"):
                            asm_args = insn.asm_args
                        elif inspect.ismethod(insn):
                            asm_args = list(inspect.signature(insn).parameters)
                        assert len(args) == len(
                            asm_args
                        ), f"args {args!r} don't fit insn args {asm_args!r}"
                        args = translate_arg(args, asm_args)
                        ops = insn(**args)
                        if not isinstance(ops, list):
                            ops = [ops]
                        for op in ops:
                            self._body.append(op & 0xFFFF)
                            self._body.append(op >> 16)
                    case st.Pragma(kind="assert", args=args) | st.Pragma(
                        kind="assert~", args=args
                    ):
                        self._rest_unwritten = not line.kind.endswith("~")
                        asserts = parse_pairs(args)
                        if self._results is None:
                            self.run_st_sim()
                            faultcode = asserts.pop(
                                "faultcode", FaultCode.ILLEGAL_INSTRUCTION
                            )
                            self.assertReg(
                                "faultcode",
                                faultcode,
                            )
                            self.assertReg(
                                "faultinsn",
                                int(
                                    asserts.pop(
                                        "faultinsn",
                                        (
                                            "0xFFFFFFFF"
                                            if faultcode
                                            == FaultCode.ILLEGAL_INSTRUCTION
                                            else "0"
                                        ),
                                    ),
                                    0,
                                ),
                            )
                        for reg, assign in asserts.items():
                            self.assertReg(reg, assign)
                    case st.Pragma(kind="half", args=[h]):
                        self._body.append(h & 0xFFFF)
                    case st.Pragma(kind="word", args=[w]):
                        self._body.append(w & 0xFFFF)
                        self._body.append((w >> 16) & 0xFFFF)
                    case st.Pragma(kind="rtf", args=[f, *pairs]):
                        self.init_st(
                            pairs,
                            body=Hart.sysmem_init_for(
                                Path(__file__).parent / f.decode()
                            ),
                        )
                    case _:
                        print("idk how to handle", line)
                        raise RuntimeError("weh")
        self.fish_st()

    def run_st_sim(self):
        hart = Hart(
            sysmem=Memory(
                depth=len(self._body) + 2, shape=16, init=self._body + [0xFFFF, 0xFFFF]
            ),
            reg_inits=self._reg_inits,
            track_reg_written=True,
        )
        self._results = run_until_fault(hart)
        self._body = None
        self._asserted = set(
            ["pc", "faultcode", "faultinsn"]
        )  # don't include these in 'rest'

    def fish_st(self):
        if self._rest_unwritten and self._results is not None:
            self.assertRegRest(Unwritten)

    def assertReg(self, rn, v):
        self._asserted.add(rn)
        self.assertRegValue(v, self._results.get(rn, Unwritten), rn=rn)

    def assertRegRest(self, v):
        for name, result in self._results.items():
            if name in self._asserted:
                continue
            self.assertRegValue(v, result, rn=name)

    def assertRegValue(self, expected, actual, *, rn=None):
        if rn is not None:
            rn = f"{rn!r}="
        if expected is Unwritten or actual is Unwritten:
            self.assertIs(
                expected, actual, f"expected {rn}{expected!r}, actual {rn}{actual!r}"
            )
            return
        if isinstance(expected, int):
            if expected < 0:
                expected += 2**32  # XLEN
            self.assertEqual(
                expected,
                actual,
                f"expected {rn}0x{expected:X}, actual {rn}0x{actual:X}",
            )
        else:
            self.assertEqual(
                expected, actual, f"expected {rn}{expected!r}, actual {rn}{actual!r}"
            )


TEST_REPLACEMENT = re.compile(r"(?:\A|[^a-zA-Z0-9]+)[a-zA-Z0-9]")
for test_file in Path(__file__).parent.glob("test_*.st"):
    name = TEST_REPLACEMENT.sub(lambda t: t[0][-1].upper(), Path(test_file).name)
    globals()[name] = type(StTestCase)(name, (StTestCase,), {"filename": test_file})
