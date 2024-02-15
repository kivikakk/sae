from dataclasses import dataclass
from functools import singledispatchmethod
from typing import Optional

from funcparserlib.lexer import TokenSpec, make_tokenizer
from funcparserlib.parser import finished, many, maybe, tok

__all__ = ["Pragma", "Op", "Parser"]


tokenize = make_tokenizer(
    [
        TokenSpec("whitespace", r"\s+"),
        TokenSpec("comment", r";.*$"),
        TokenSpec("label", r"\w+:"),
        TokenSpec("pragma", r"\.\w+"),
        TokenSpec("register", "pc|x[0-9]|x[12][0-9]|x3[01]"),
        TokenSpec("word", r"[a-zA-Z][a-zA-Z0-9_.]*"),
        TokenSpec("number", r"(-\s*)?(0[xX][0-9a-fA-F_]+|0[bB][01_]+|[0-9_]+)"),
        TokenSpec("comma", r","),
        TokenSpec("equals", r"="),
    ]
)


@dataclass
class Register:
    register: str


@dataclass
class Label:
    label: str


@dataclass
class Assign:
    register: Register
    assign: int


@dataclass
class Pragma:
    kind: str
    args: list[Register | Assign | int]
    line: str
    lineno: int


@dataclass
class Op:
    opcode: str
    args: list[Register | int]
    line: str
    lineno: int


def parse(tokens, *, line, lineno):
    number = tok("number") >> (lambda n: int(n, 0))

    register = tok("register") >> Register
    assign = -tok("equals") + number
    register_or_assign = register + maybe(assign) >> (
        lambda p: p[0] if p[1] is None else Assign(*p)
    )

    arg = register_or_assign | number | tok("word")
    arglist = maybe(arg + many(-tok("comma") + arg)) >> (
        lambda p: [] if not p else [p[0]] + p[1]
    )

    label = tok("label") >> (lambda l: Label(l[:-1]))
    pragma = tok("pragma") + arglist >> (
        lambda p: Pragma(p[0][1:], p[1], line=line, lineno=lineno)
    )
    op = tok("word") + arglist >> (lambda p: Op(*p, line=line, lineno=lineno))

    stmt = label | pragma | op

    document = stmt + -finished

    return document.parse(tokens)


class Parser:
    begun: bool
    test_name: Optional[str]
    test_body: Optional[list[Pragma | Op]]
    lineno: int

    results: list[tuple[str, list[Pragma | Op]]]

    def __init__(self):
        self.begun = False
        self.test_name = None
        self.test_body = None
        self.lineno = 0

        self.results = []

    @singledispatchmethod
    def feed(self, line):
        self.lineno += 1
        tokens = [
            token
            for token in tokenize(line)
            if token.type not in {"whitespace", "comment"}
        ]
        if not tokens:
            return
        parsed = parse(tokens, line=line, lineno=self.lineno)

        if not self.begun:
            match parsed:
                case Label(label=label):
                    self.test_name = label
                    self.test_body = []
                    self.begun = True
                case _:
                    raise RuntimeError(f"what's {line!r} (in !begun), precious?")
        match parsed:
            case Pragma() | Op():
                self.test_body.append(parsed)
            case Label(label=label):
                self.fish()
                self.test_name = label
                self.test_body = []
            case _:
                raise RuntimeError(f"what's {line!r}, precious?")

    @feed.register(list)
    def feed_list(self, list):
        for item in list:
            self.feed(item.strip())
        self.fish()

    def fish(self):
        self.results.append((self.test_name, self.test_body))
