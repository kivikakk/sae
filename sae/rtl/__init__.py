from dataclasses import dataclass

from amaranth import Module, ResetInserter, Signal
from amaranth.lib.wiring import Component, In, Out

from ..targets import cxxrtl, icebreaker
from .hart import Hart

__all__ = ["Top"]


class Top(Component):
    def __init__(self, *args, platform, **kwargs):
        self.hart = Hart(*args, **kwargs)

        match platform:
            case cxxrtl():
                super().__init__({
                    "uart_rx": In(1),
                    "uart_tx": Out(1),
                })

            case _:
                super().__init__({})

    def elaborate(self, platform):
        m = Module()

        rst = Signal()
        m.d.sync += rst.eq(0)

        match platform:
            case icebreaker():
                plat_button = platform.request("button")
                with m.If(plat_button.i):
                    m.d.sync += rst.eq(1)

                self.hart.plat_uart = platform.request("uart")

            case cxxrtl():
                @dataclass
                class FakeUartPin:
                    i: Signal = None
                    o: Signal = None

                @dataclass
                class FakeUart:
                    rx: FakeUartPin
                    tx: FakeUartPin

                self.hart.plat_uart = FakeUart(
                    rx=FakeUartPin(i=self.uart_rx), tx=FakeUartPin(o=self.uart_tx))

        m.submodules.hart = ResetInserter(rst)(self.hart)

        return m
