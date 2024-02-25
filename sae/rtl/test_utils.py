from functools import singledispatch
from pathlib import Path

from amaranth import Fragment, Memory
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick
from rainhdx import Platform

from . import State, Top
from .rv32 import Reg
from .test_mmu import pms

__all__ = ["run_until_fault", "Unwritten", "InsnTestHelpers"]


@singledispatch
def run_until_fault(top, *, max_cycles=1000):
    results = {}

    def bench():
        uart_buffer = (top.reg_inits or {}).get("uart")
        if uart_buffer:
            yield top.uart.rd_rdy.eq(1)
            yield top.uart.rd_data.eq(uart_buffer[0])
            uart_buffer = uart_buffer[1:]

        nonlocal results
        first = True
        insn = None
        cycles = -1
        written = set()
        uart = bytearray()
        while State.RUNNING == (yield top.state):
            if first:
                first = False
            else:
                yield Tick()
            if (yield top.uart.wr_en):
                uart.append((yield top.uart.wr_data))
            if (yield top.uart.rd_en):
                if uart_buffer:
                    yield top.uart.rd_data.eq(uart_buffer[0])
                    uart_buffer = uart_buffer[1:]
                else:
                    yield top.uart.rd_data.eq(0)
                    yield top.uart.rd_rdy.eq(0)

            last_insn, insn = insn, (yield top.insn)
            if insn != last_insn:
                if cycles == max_cycles:
                    raise RuntimeError("max cycles reached")
                cycles += 1
                print(f"pc={(yield top.pc):08x} [{insn:0>8x}]", end="")
                for i in range(1, 32):
                    v = yield top.xreg[i]
                    if i in written or v:
                        written.add(i)
                        rn = Reg[f"X{i}"].friendly
                        print(f"  {rn}={(yield top.xreg[i]):08x}", end="")
                print()
                yield from pms(
                    mr=top.mmu.mmu_read,
                    mw=top.mmu.mmu_write,
                    sysmem=top.sysmem,
                    prefix="  ",
                )
                print()

        results["pc"] = yield top.pc
        for i in range(1, 32):
            if not top.track_reg_written or (yield top.xreg_written[i]):
                results[Reg[f"X{i}"]] = yield top.xreg[i]
        results["faultcode"] = yield top.fault_code
        results["faultinsn"] = yield top.fault_insn
        if uart:
            results["uart"] = bytes(uart)

    sim = Simulator(Fragment.get(top, platform=Platform["test"]))
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results


@run_until_fault.register(Path)
def run_until_fault_bin(path, *, memory=8192, **kwargs):
    return run_until_fault(Top(sysmem=Top.sysmem_for(path, memory=memory), **kwargs))


@run_until_fault.register(list)
def run_until_fault_por(mem, **kwargs):
    return run_until_fault(
        Top(sysmem=Memory(depth=len(mem), shape=16, init=mem), **kwargs)
    )


class UnwrittenClass:
    def __repr__(self):
        return "Unwritten"


Unwritten = UnwrittenClass()


class InsnTestHelpers:
    def __init__(self, *args):
        super().__init__(*args)
        self.body = None
        self.results = None

    def run_body(self, regs):
        top = Top(
            sysmem=Memory(
                depth=len(self.body) + 2, shape=16, init=self.body + [0xFFFF, 0xFFFF]
            ),
            reg_inits=regs,
            track_reg_written=True,
        )
        self.results = run_until_fault(top)
        self.body = None
        self.__asserted = set(
            ["pc", "faultcode", "faultinsn"]
        )  # don't include these in 'rest'

    def assertReg(self, rn, v):
        self.__asserted.add(rn)
        self.assertRegValue(v, self.results.get(rn, Unwritten), rn=rn)

    def assertRegRest(self, v):
        for name, result in self.results.items():
            if name in self.__asserted:
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
