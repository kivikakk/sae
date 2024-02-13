from contextlib import contextmanager
from functools import partialmethod

from amaranth import C
from amaranth.hdl.mem import Memory
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

    def __ensureInBody(self):
        assert self.__body is not None

    def __ensureRun(self):
        assert self.__results is not None

    def assertReg(self, r, v):
        self.__ensureRun()
        rn = f"x{int(r)}"
        self.__asserted.add(rn)
        self.assertRegValue(v, self.__results.get(rn, Unwritten))

    def assertRegRest(self, v):
        self.__ensureRun()
        for name, result in self.__results.items():
            if name in self.__asserted:
                continue
            self.assertRegValue(v, result)

    def assertRegValue(self, expected, actual):
        if expected is Unwritten:
            self.assertIs(actual, Unwritten)
            return
        if expected < 0:
            expected += 2**32
        self.assertEqual(expected, actual)

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


for op in ["addi", "slti", "sltiu", "andi", "ori", "xori"]:

    def f(self, op, rs1, rd, imm):
        self._InsnTestHelpers__ensureInBody()
        self._InsnTestHelpers__body.append(
            InsI(Opcode.OP_IMM, OpImmFunct[op.upper()], rs1, rd, C(imm, 12))
        )

    name = op[0].upper() + op[1:]
    f.__name__ = name
    setattr(InsnTestHelpers, name, partialmethod(f, op))
