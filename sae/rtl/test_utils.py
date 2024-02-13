from amaranth import C
from amaranth.hdl.mem import Memory
from amaranth.sim import Simulator, Tick
from contextlib import contextmanager

from . import InsI, Opcode, OpImmFunct, State, Top, Reg

__all__ = ["run_until_fault", "Unchanged", "InsnTestHelpers"]


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
                for i in range(1, 4):
                    print(f"  x{i}={(yield top.xreg[i]):08x}", end="")
                print()

        results["pc"] = yield top.pc
        for i in range(1, 32):
            results[f"x{i}"] = yield top.xreg[i]

    sim = Simulator(top)
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results


Unchanged = object()


class InsnTestHelpers:
    def __init__(self, *args):
        super().__init__(*args)
        self.__body = None

    @contextmanager
    def Run(self):
        self.__body = []
        yield
        top = Top(
            sysmem=Memory(width=32, depth=len(self.__body) + 1, init=self.__body + [0])
        )
        self.__results = run_until_fault(top)
        self.__body = None
        self.__asserted = set(["pc"])  # don't assume "rest" includes pc

    def __ensureInBody(self):
        assert self.__body is not None

    def __ensureRun(self):
        assert self.__results is not None

    def Addi(self, rs1, rd, imm):
        self.__ensureInBody()
        self.__body.append(InsI(Opcode.OP_IMM, OpImmFunct.ADDI, rs1, rd, C(imm, 12)))

    def assertReg(self, r, v):
        self.__ensureRun()
        rn = f"x{int(r)}"
        self.__asserted.add(rn)
        self.assertRegValue(v, self.__results[rn])

    def assertRegRest(self, v):
        self.__ensureRun()
        for name, result in self.__results.items():
            if name in self.__asserted:
                continue
            self.assertRegValue(v, result)

    def assertRegValue(self, expected, actual):
        # XXX: we don't actually check for unchanged yet
        if expected is Unchanged:
            expected = 0
        self.assertEqual(expected, actual)

    def assertRegs(self, *pairs):
        for r, v in pairs:
            if r[0] == "x":
                self.assertReg(Reg[f"X{r[1:]}"], v)
            elif r == "rest":
                self.assertRegRest(v)
            else:
                raise NotImplementedError(r)
