from functools import singledispatch
from pathlib import Path

from amaranth import Fragment
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator

from sae.rtl.hart import AccessWidth, Hart, State
from sae.rtl.rv32 import Reg, disasm
from sae.targets import test

__all__ = ["run_until_fault", "print_mmu"]

SYSMEM_TO_SHOW = 8


@singledispatch
def run_until_fault(hart: Hart, *, max_cycles=1000):
    results = {}

    async def bench(ctx):
        uart = hart.mmu.peripherals[0x0001]

        uart_send = (hart.reg_inits or {}).get("uart")
        if uart_send:
            ctx.set(uart.rd.valid, 1)
            ctx.set(uart.rd.payload, uart_send[0])
            uart_send = uart_send[1:]

        nonlocal results
        first = True
        cycles = -1
        written = set()
        uart_recv = bytearray()
        while State.RUNNING == ctx.get(hart.state):
            if first:
                first = False
            else:
                await ctx.tick()
            if ctx.get(uart.wr.valid):
                datum = ctx.get(uart.wr.payload)
                print(f"core wrote to UART: 0x{datum:0>2x} '{datum:c}'")
                uart_recv.append(datum)
            if ctx.get(uart.rd.ready):
                if uart_send:
                    print(f"core read from UART: 0x{uart_send[0]:0>2x} '{uart_send[0]:c}'")
                    ctx.set(uart.rd.payload, uart_send[0])
                    uart_send = uart_send[1:]
                else:
                    print(f"core read from empty UART ({uart_send!r})")
                    ctx.set(uart.rd.payload, 0)
                    ctx.set(uart.rd.valid, 0)

            if ctx.get(hart.resolving):
                if cycles == max_cycles:
                    raise RuntimeError("max cycles reached")
                cycles += 1
                insn = ctx.get(hart.insn)
                print(f"pc={ctx.get(hart.pc):08x} [{insn:0>8x}]  {disasm(insn):<20}", end="")
                for i in range(1, 32):
                    v = ctx.get(hart.xmem.data[i])
                    if i in written or v:
                        written.add(i)
                        rn = Reg[f"X{i}"].friendly
                        print(f"  {rn}={ctx.get(hart.xmem.data[i]):08x}", end="")
                print()
                print_mmu(ctx, mr=hart.mmu.read, mw=hart.mmu.write, sysmem=hart.sysmem, prefix="  ")
                print()

        results["pc"] = ctx.get(hart.pc)
        for i in range(1, 32):
            if not hart.track_reg_written or ctx.get(hart.xreg_written[i]):
                results[Reg[f"X{i}"]] = ctx.get(hart.xmem.data[i])
        results["faultcode"] = ctx.get(hart.fault_code)
        results["faultinsn"] = ctx.get(hart.fault_insn)
        if uart_recv:
            results["uart"] = bytes(uart_recv)

    sim = Simulator(Fragment.get(hart, platform=test()))
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


def print_mmu(ctx, *, mr=None, mw=None, sysmem=None, prefix=""):
    if mr:
        print(
            f"{prefix}MR: "
            f"a={ctx.get(mr.req.payload.addr):0>8x}  w={AccessWidth(ctx.get(mr.req.payload.width)).name}  "
            f"v={ctx.get(mr.resp.payload):0>8x}  v={ctx.get(mr.resp.valid):b}        ",
            end="",
        )
        if sysmem:
            print("data=", end="")
            for i in range(min(SYSMEM_TO_SHOW, sysmem.depth)):
                print(f"{ctx.get(sysmem.data[i]):0>4x} ", end="")
        print()
    if mw:
        print(
            f"{prefix}MW: "
            f"a={ctx.get(mw.req.payload.addr):0>8x}  w={AccessWidth(ctx.get(mw.req.payload.width)).name}  "
            f"d={ctx.get(mw.req.payload.data):0>8x}  r={ctx.get(mw.req.ready):b}  a={ctx.get(mw.req.valid):b}   ",
            end="",
        )
        if sysmem and not mr:
            print("data=", end="")
            for i in range(min(SYSMEM_TO_SHOW, sysmem.depth)):
                print(f"{ctx.get(sysmem.data[i]):0>4x} ", end="")
        print()
