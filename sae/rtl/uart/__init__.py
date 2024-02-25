from amaranth import Module
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.io import Pin
from amaranth.lib.wiring import Component, In, Out
from amaranth_stdio.serial import AsyncSerial

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

    def elaborate(self, platform):
        m = Module()

        if platform.simulation:
            return m

        freq = getattr(platform, "default_clk_frequency", 1e6)

        m.submodules.fifo = self._fifo = SyncFIFO(width=8, depth=32)
        m.d.comb += [
            self._fifo.w_data.eq(self.wr_data),
            self._fifo.w_en.eq(self.wr_en),
        ]

        m.submodules.serial = serial = AsyncSerial(
            divisor=int(freq // self._baud), pins=self._plat_uart
        )

        # tx
        with m.FSM() as fsm:
            with m.State("idle"):
                with m.If(serial.tx.rdy & self._fifo.r_rdy):
                    m.d.sync += serial.tx.data.eq(self._fifo.r_data)
                    m.next = "wait"

            with m.State("wait"):
                # actually need this lol
                m.next = "idle"

            m.d.comb += [
                serial.tx.ack.eq(fsm.ongoing("wait")),
                self._fifo.r_en.eq(fsm.ongoing("wait")),
            ]

        # rx
        with m.FSM() as fsm:
            with m.State("idle"):
                with m.If(serial.rx.rdy):
                    m.next = "read"

            with m.State("read"):
                m.d.sync += self.rd_data.eq(serial.rx.data)
                m.next = "consume"

            with m.State("consume"):
                with m.If(self.rd_en):
                    m.next = "idle"

            m.d.comb += [
                serial.rx.ack.eq(fsm.ongoing("idle")),
                self.rd_rdy.eq(fsm.ongoing("consume")),
            ]

        return m
