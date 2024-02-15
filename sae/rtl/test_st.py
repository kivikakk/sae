import re
import unittest
from contextlib import contextmanager
from enum import Enum
from functools import singledispatchmethod
from itertools import chain
from pathlib import Path
from typing import Any, Optional

from . import Top
from .rv32 import INSNS, Reg
from .test_utils import InsnTestHelpers, Unwritten


class ParserState(Enum):
    Start = 0
    TestBody = 1


RE_EMPTY = re.compile(r"\A\s* (?:;.*)? \Z", re.VERBOSE)
RE_TEST_START = re.compile(r"\A (\w+): \s* (?:;.*)? \Z", re.VERBOSE)
RE_TEST_PRAGMA = re.compile(
    r"""
    \A\s* \.(\w+)
    (?:
      \s+
      (
        (?:\w+) \s* (?: =\s* (?:-?\s*\w+))?
        (?: \s*,\s* (?:\w+) \s* (?: =\s* (?:-?\s*\w+))? )*
      )
    )?
    \s* (?:;.*)? \Z
""",
    re.VERBOSE,
)
RE_TEST_PRAGMA_PAIR = re.compile(r" (\w+) \s* (?: =\s* ((?:-\s*)?\w+))? ", re.VERBOSE)
RE_TEST_OP = re.compile(
    r"""
    \A\s*
    (\w+)
    (?:
      \s+
      (
        (?:\w+)
        (?: \s*,\s* (?:-?\s*\w+) )*
      )
    )?
    \s* (?:;.*)? \Z
""",
    re.VERBOSE,
)
RE_TEST_OP_ARG = re.compile(r" ((?:-\s*)?\w+) ", re.VERBOSE)


class Pragma:
    kind: str
    args: list[Any]
    kwargs: dict[str, Any]
    line: str
    lineno: int

    def __init__(self, kind, pairs, *, line, lineno):
        self.kind = kind
        self.args = []
        self.kwargs = {}
        if any(pairs.values()):
            self.kwargs = pairs
        elif pairs:
            self.args = list(pairs.keys())
        self.line = line
        self.lineno = lineno

    def __repr__(self):
        items = chain(
            (str(arg) for arg in self.args),
            (f"{k}={v}" for k, v in self.kwargs.items()),
        )
        return f'{self.kind}({", ".join(items)})'


class Op:
    opcode: str
    args: list[str]
    line: str
    lineno: int

    def __init__(self, opcode, args, *, line, lineno):
        self.opcode = opcode
        self.args = args
        self.line = line
        self.lineno = lineno

    def __repr__(self):
        return f'op({self.opcode} {", ".join(self.args)})'


class StParser:
    state: ParserState
    test_name: Optional[str]
    test_body: Optional[list[Pragma | Op]]
    lineno: int

    results: list[tuple[str, list[Pragma | Op]]]

    def __init__(self):
        self.state = ParserState.Start
        self.test_name = None
        self.test_body = None
        self.lineno = 0

        self.results = []

    @singledispatchmethod
    def feed(self, line):
        self.lineno += 1
        match self.state:
            case ParserState.Start:
                if groups := RE_TEST_START.match(line):
                    self.test_name = groups[1]
                    self.test_body = []
                    self.state = ParserState.TestBody
                elif not RE_EMPTY.match(line):
                    raise RuntimeError(f"what's {line!r}, precious?")
            case ParserState.TestBody:
                assert self.test_body is not None
                if groups := RE_TEST_PRAGMA.match(line):
                    kind = groups[1]
                    pairs = {}
                    if groups[2] is not None:
                        for m in RE_TEST_PRAGMA_PAIR.finditer(groups[2]):
                            pairs[m[1]] = m[2]
                    self.test_body.append(
                        Pragma(kind, pairs, line=line, lineno=self.lineno)
                    )
                elif groups := RE_TEST_OP.match(line):
                    opcode = groups[1]
                    if groups[2] is not None:
                        args = RE_TEST_OP_ARG.findall(groups[2])
                    else:
                        args = []
                    self.test_body.append(
                        Op(opcode, args, line=line, lineno=self.lineno)
                    )
                elif groups := RE_TEST_START.match(line):
                    self.fish()
                    self.test_name = groups[1]
                    self.test_body = []
                elif not RE_EMPTY.match(line):
                    raise RuntimeError(f"what's {line!r}, precious?")

    @feed.register(list)
    def feed_list(self, list):
        for item in list:
            self.feed(item.strip())
        self.fish()

    def fish(self):
        self.results.append((self.test_name, self.test_body))


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


class StTestCase(InsnTestHelpers, unittest.TestCase):
    def __init_subclass__(cls):
        super().__init_subclass__()

        parser = StParser()
        with open(Path(__file__).parent / cls.filename, "r") as f:
            parser.feed(f.readlines())

        for name, body in parser.results:
            name = f"test_st_{name}"
            setattr(cls, name, lambda self, body=body: cls.run_st(self, body))

    @singledispatchmethod
    @classmethod
    def translate_arg(cls, arg):
        if arg[0] == "x":
            return Reg[f"X{arg[1:]}"]
        elif arg == "ra":
            return Reg.X1
        return int(arg, 0)

    @translate_arg.register(list)
    def translate_arg_list(cls, args):
        return [cls.translate_arg(arg) for arg in args]

    def run_st(self, body):
        for line in body:
            with annotate_exceptions(self.filename, line):
                match line:
                    case Pragma(kind="init", kwargs=kwargs):
                        self.__fish()
                        self.__reg_inits = {k: int(v, 0) for k, v in kwargs.items()}
                        self.body = []
                        self.results = None
                    case Op(opcode=opcode, args=args):
                        insn = INSNS[opcode[0].upper() + opcode[1:]]
                        args = self.translate_arg(args)
                        ops = insn(*args)
                        if not isinstance(ops, list):
                            ops = [ops]
                        self.body.extend(ops)
                    case Pragma(kind="assert", kwargs=kwargs):
                        if self.results is None:
                            self.run_body(self.__reg_inits)
                        for k, v in kwargs.items():
                            assert k[0] == "x"
                            self.assertReg(int(k[1:]), int(v, 0))
                    case Pragma(kind="word", args=[w]):
                        self.body.append(int(w, 0))
                    case _:
                        print("idk how to handle", line)
                        raise RuntimeError("weh")

    def __fish(self):
        if self.results is not None:
            self.assertRegRest(Unwritten)


class TestSemanticsSt(StTestCase):
    filename = "test_semantics.st"
