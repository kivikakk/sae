from functools import singledispatch
from pathlib import Path

from amaranth import Fragment, Memory
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick
from rainhdx import Platform

from . import Hart, State
from .mmu import AccessWidth
from .rv32 import Reg, disasm

__all__ = ["run_until_fault", "print_mmu"]

SYSMEM_TO_SHOW = 8


@singledispatch
def run_until_fault(hart, *, max_cycles=1000):
    results = {}

    def bench():
        uart_buffer = (hart.reg_inits or {}).get("uart")
        if uart_buffer:
            yield hart.uart.rd_rdy.eq(1)
            yield hart.uart.rd_data.eq(uart_buffer[0])
            uart_buffer = uart_buffer[1:]

        nonlocal results
        first = True
        cycles = -1
        written = set()
        uart = bytearray()
        while State.RUNNING == (yield hart.state):
            if first:
                first = False
            else:
                yield Tick()
            if (yield hart.uart.wr_en):
                datum = yield hart.uart.wr_data
                print(f"core wrote to UART: 0x{datum:0>2x} '{datum:c}'")
                uart.append(datum)
            if (yield hart.uart.rd_en):
                if uart_buffer:
                    print(
                        f"core read from UART: 0x{uart_buffer[0]:0>2x} '{uart_buffer[0]:c}'"
                    )
                    yield hart.uart.rd_data.eq(uart_buffer[0])
                    uart_buffer = uart_buffer[1:]
                else:
                    print("core read from empty UART")
                    yield hart.uart.rd_data.eq(0)
                    yield hart.uart.rd_rdy.eq(0)

            if (yield hart.resolving):
                if cycles == max_cycles:
                    raise RuntimeError("max cycles reached")
                cycles += 1
                insn = yield hart.insn
                print(
                    f"pc={(yield hart.pc):08x} [{insn:0>8x}]  {disasm(insn):<20}",
                    end="",
                )
                for i in range(1, 32):
                    v = yield hart.xreg[i]
                    if i in written or v:
                        written.add(i)
                        rn = Reg[f"X{i}"].friendly
                        print(f"  {rn}={(yield hart.xreg[i]):08x}", end="")
                print()
                yield from print_mmu(
                    mr=hart.mmu.mmu_read,
                    mw=hart.mmu.mmu_write,
                    sysmem=hart.sysmem,
                    prefix="  ",
                )
                print()

        results["pc"] = yield hart.pc
        for i in range(1, 32):
            if not hart.track_reg_written or (yield hart.xreg_written[i]):
                results[Reg[f"X{i}"]] = yield hart.xreg[i]
        results["faultcode"] = yield hart.fault_code
        results["faultinsn"] = yield hart.fault_insn
        if uart:
            results["uart"] = bytes(uart)

    sim = Simulator(Fragment.get(hart, platform=Platform["test"]))
    sim.add_clock(1e6)
    sim.add_testbench(bench)
    sim.run()

    return results


@run_until_fault.register(Path)
def run_until_fault_bin(path, *, memory=8192, **kwargs):
    return run_until_fault(Hart(sysmem=Hart.sysmem_for(path, memory=memory), **kwargs))


@run_until_fault.register(list)
def run_until_fault_por(mem, **kwargs):
    return run_until_fault(
        Hart(sysmem=Memory(depth=len(mem), shape=16, init=mem), **kwargs)
    )


def print_mmu(*, mr=None, mw=None, sysmem=None, prefix=""):
    if mr:
        print(
            f"{prefix}MR: "
            f"a={(yield mr.read.addr):0>8x}  w={AccessWidth((yield mr.read.width))}  "
            f"v={(yield mr.read.value):0>8x}  v={(yield mr.read.valid):b}        ",
            end="",
        )
        if sysmem:
            print("data=", end="")
            for i in range(min(SYSMEM_TO_SHOW, sysmem.depth)):
                print(f"{(yield sysmem[i]):0>4x} ", end="")
        print()
    if mw:
        print(
            f"{prefix}MW: "
            f"a={(yield mw.write.addr):0>8x}  w={AccessWidth((yield mw.write.width))}  "
            f"d={(yield mw.write.data):0>8x}  r={(yield mw.write.rdy):b}  a={(yield mw.write.ack):b}   ",
            end="",
        )
        if sysmem and not mr:
            print("data=", end="")
            for i in range(min(SYSMEM_TO_SHOW, sysmem.depth)):
                print(f"{(yield sysmem[i]):0>4x} ", end="")
        print()
