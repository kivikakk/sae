import inspect
import re
import unittest
from contextlib import contextmanager
from functools import singledispatchmethod
from pathlib import Path
from typing import Optional

from .. import st
from . import FaultCode, Hart
from .rv32 import INSNS, Reg
from .test_utils import InsnTestHelpers, Unwritten


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

        parser = st.Parser()
        with open(Path(__file__).parent / cls.filename, "r") as f:
            parser.feed(f.readlines())

        for name, body in parser.results:
            if name.startswith("test_"):
                setattr(cls, name, lambda self, body=body: cls.run_st(self, body))

    @singledispatchmethod
    @classmethod
    def translate_arg(cls, arg, name):
        if isinstance(arg, st.Register):
            return Reg(arg.register.upper())
        elif isinstance(arg, (int, st.Offset)):
            return arg
        elif name in ("pred", "succ"):
            return arg
        raise RuntimeError(f"arg weh {name!r} = {arg!r}")

    @translate_arg.register(list)
    def translate_arg_list(cls, args, names):
        return [cls.translate_arg(arg, name) for arg, name in zip(args, names)]

    def _init_st(self, *, body=None, reg_inits=None):
        if hasattr(self, "_rest_unwritten"):
            self._fish_st()
        self._reg_inits = reg_inits or {}
        self.body = body or []
        self.results = None
        self._rest_unwritten = True

    @staticmethod
    def _parse_pairs(args):
        return {
            (
                assign.register
                if isinstance(assign.register, str)
                else Reg(assign.register.register.upper())
            ): assign.assign
            for assign in args
        }

    def run_st(self, body):
        for line in body:
            with annotate_exceptions(self.filename, line):
                match line:
                    case st.Pragma(kind="init", args=args):
                        self._init_st(reg_inits=self._parse_pairs(args))
                    case st.Op(opcode=opcode, args=args):
                        insn = INSNS[opcode[0].upper() + opcode[1:]]
                        args = self.translate_arg(
                            args, inspect.signature(insn).parameters.keys()
                        )
                        ops = insn(*args)
                        if not isinstance(ops, list):
                            ops = [ops]
                        self.body.extend(ops)
                    case st.Pragma(kind="assert", args=args) | st.Pragma(
                        kind="assert~", args=args
                    ):
                        self._rest_unwritten = not line.kind.endswith("~")
                        asserts = self._parse_pairs(args)
                        if self.results is None:
                            self.run_body(self._reg_inits)
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
                                        "0xFFFFFFFF"
                                        if faultcode == FaultCode.ILLEGAL_INSTRUCTION
                                        else "0",
                                    ),
                                    0,
                                ),
                            )
                        for reg, assign in asserts.items():
                            self.assertReg(reg, assign)
                    case st.Pragma(kind="word", args=[w]):
                        self.body.append(w & 0xFFFF)
                        self.body.append((w >> 16) & 0xFFFF)
                    case st.Pragma(kind="rtf", args=[f, *pairs]):
                        self._init_st(
                            body=Hart.sysmem_init_for(
                                Path(__file__).parent / f.decode()
                            ),
                            reg_inits=self._parse_pairs(pairs),
                        )
                    case _:
                        print("idk how to handle", line)
                        raise RuntimeError("weh")
        self._fish_st()

    def _fish_st(self):
        if self._rest_unwritten and self.results is not None:
            self.assertRegRest(Unwritten)


TEST_REPLACEMENT = re.compile(r"(?:\A|[^a-zA-Z]+)[a-zA-Z]")
for test_file in Path(__file__).parent.glob("test_*.st"):
    name = TEST_REPLACEMENT.sub(lambda t: t[0][-1].upper(), Path(test_file).name)
    globals()[name] = type(StTestCase)(name, (StTestCase,), {"filename": test_file})  # type: ignore
