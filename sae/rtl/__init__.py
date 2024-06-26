from amaranth import Elaboratable, Module, ResetInserter, Signal

from ..targets import icebreaker
from .hart import Hart

__all__ = [
    "Top",
]


class Top(Elaboratable):
    def __init__(self, *args, **kwargs):
        self.hart = Hart(*args, **kwargs)

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

        m.submodules.hart = ResetInserter(rst)(self.hart)

        return m
