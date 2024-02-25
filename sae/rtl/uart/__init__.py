from amaranth import Module
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.io import Pin
from amaranth.lib.wiring import Component, In, Out
from amaranth_stdio.serial import AsyncSerialTX

__all__ = ["UART"]


class UART(Component):
    wr_data: In(8)
    wr_en: In(1)

    rd_rdy: Out(1)
    rd_en: In(1)
    rd_data: Out(8)

    _plat_uart: Pin
    _baud: int
    _fifo: SyncFIFO

    def __init__(self, plat_uart, baud=9600):
        self._plat_uart = plat_uart
        self._baud = baud
        super().__init__()
        self._fifo = SyncFIFO(width=8, depth=32)

    def elaborate(self, platform):
        m = Module()

        freq = getattr(platform, "default_clk_frequency", 1e6)

        m.submodules.fifo = self._fifo
        m.d.comb += [
            self._fifo.w_data.eq(self.wr_data),
            self._fifo.w_en.eq(self.wr_en),
        ]

        m.submodules.astx = astx = AsyncSerialTX(
            divisor=int(freq // self._baud), pins=self._plat_uart
        )
        m.d.sync += [
            astx.ack.eq(0),
            self._fifo.r_en.eq(0),
        ]

        with m.FSM():
            with m.State("idle"):
                with m.If(astx.rdy & self._fifo.r_rdy):
                    m.d.sync += [
                        astx.data.eq(self._fifo.r_data),
                        astx.ack.eq(1),
                        self._fifo.r_en.eq(1),
                    ]
                    m.next = "wait"

            with m.State("wait"):
                # actually need this lol
                m.next = "idle"

        return m
