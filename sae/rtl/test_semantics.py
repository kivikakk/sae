import unittest

from amaranth import C, Memory

from . import InsI, InsIS, Opcode, OpImmFunct, Reg, State, Top, test_utils

__all__ = ["TestInsns"]


Unchanged = object()


def insn_test(fn):
    def inner(self, *, body, expected):
        top = Top(sysmem=Memory(width=32, depth=len(body) + 1, init=body + [0]))
        results = test_utils.run_until_fault(top)

        rest = {}
        rest_handler = None
        for reg, value in expected.items():
            if reg[0] == "x":
                # XXX: we don't actually check for unchanged yet
                if value is Unchanged:
                    value = 0
                self.assertEqual(value, results[f"x{int(reg[1:])}"])
            elif reg == "rest":
                rest_handler = value
            else:
                rest[reg] = value

        if rest_handler is not None:
            for reg, value in rest.items():
                # XXX: as above
                if value is Unchanged:
                    value = 0
                self.assertEqual(value, results[f"x{int(reg[1:])}"])

    def outer(self):
        return inner(self, **fn(self))

    return outer


class TestInsns(unittest.TestCase):
    @insn_test
    def test_insn_addi(self):
        return {
            "body": [
                # ADDI x1, x0, 3 (= MV x1, 3)
                InsI(Opcode.OP_IMM, OpImmFunct.ADDI, Reg.X0, Reg.X1, C(3, 12)),
                # ADDI x2, x1, 5
                InsI(Opcode.OP_IMM, OpImmFunct.ADDI, Reg.X1, Reg.X2, C(5, 12)),
            ],
            "expected": {
                "x1": 3,
                "x2": 8,
                "rest": Unchanged,
            },
        }
