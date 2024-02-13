from contextlib import contextmanager
from functools import partialmethod

from amaranth import Memory
from amaranth.sim import Simulator, Tick

from . import InsI, Opcode, OpImmFunct, Reg, State, Top

__all__ = ["run_until_fault", "Unwritten", "InsnTestHelpers"]


def run_until_fault(top):
    results = {}

    def bench():
        nonlocal results
        first = True
        pc = None
        print()
        while State.RUNNING == (yield top.state):
            if first:
                first = False
            else:
                yield Tick()
            last_pc, pc = pc, (yield top.pc)
            if pc != last_pc:
                print(f"pc={pc:08x}  ", end="")
                for i in range(1, 6):
                    print(f"  x{i}={(yield top.xreg[i]):08x}", end="")
                print()

        results["pc"] = yield top.pc
        for i in range(1, 32):
            if not top.track_reg_written or (yield top.xreg_written[i]):
                results[f"x{i}"] = yield top.xreg[i]

    sim = Simulator(top)
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results


class UnwrittenClass:
    def __repr__(self):
        return "Unwritten"


Unwritten = UnwrittenClass()


class InsnTestHelpers:
    def __init__(self, *args):
        super().__init__(*args)
        self.__body = None

    @contextmanager
    def Run(self, **regs):
        self.__body = []
        yield
        top = Top(
            sysmem=Memory(width=32, depth=len(self.__body) + 1, init=self.__body + [0]),
            reg_inits=regs,
            track_reg_written=True,
        )
        self.__results = run_until_fault(top)
        self.__body = None
        self.__asserted = set(["pc"])  # don't assume "rest" includes pc

    def __append(self, *insns):
        assert self.__body is not None
        self.__body.extend(insns)

    def assertReg(self, r, v):
        rn = f"x{int(r)}"
        self.__asserted.add(rn)
        self.assertRegValue(v, self.__results.get(rn, Unwritten))

    def assertRegRest(self, v):
        for name, result in self.__results.items():
            if name in self.__asserted:
                continue
            self.assertRegValue(v, result)

    def assertRegValue(self, expected, actual):
        if expected is Unwritten:
            self.assertIs(actual, Unwritten)
            return
        if expected < 0:
            expected += 2**32  # XLEN
        self.assertEqual(
            expected, actual, f"expected 0x{expected:X}, actual 0x{actual:X}"
        )

    def assertRegs(self, **regs):
        if "rest" not in regs:
            regs["rest"] = Unwritten
        for r, v in regs.items():
            if r[0] == "x":
                self.assertReg(Reg[f"X{r[1:]}"], v)
            elif r == "rest":
                self.assertRegRest(v)
            else:
                raise NotImplementedError(r)

    @classmethod
    def add_insn(cls, op, f):
        name = op[0].upper() + op[1:]
        f.__name__ = name
        setattr(cls, name, partialmethod(f, op))


# TODO: bounds checking on imm arguments

for op in ["addi", "slti", "sltiu", "andi", "ori", "xori"]:

    def f(self, op, rs1, rd, imm):
        if imm > 0:
            assert 0 < imm <= 0b111111111111, f"imm is {imm}"
        elif imm < 0:
            assert 0 < -imm <= 0b111111111111, f"imm is {imm}"  # XXX check

        self._InsnTestHelpers__append(
            InsI(Opcode.OP_IMM, OpImmFunct[op.upper()], rs1, rd, imm)
        )

    InsnTestHelpers.add_insn(op, f)

for op in ["slli", "srli", "srai"]:

    def f(self, op, rs1, rd, shamt):
        assert 0 <= shamt <= 0b11111, f"shamt is {shamt}"

        funct, imm11_5 = {
            "slli": ("SLLI", 0),
            "srli": ("SRI", 0b0000000),
            "srai": ("SRI", 0b0100000),
        }[op]
        self._InsnTestHelpers__append(
            InsI(
                Opcode.OP_IMM,
                OpImmFunct[funct],
                rs1,
                rd,
                (imm11_5 << 5) | shamt,
            )
        )

    InsnTestHelpers.add_insn(op, f)
