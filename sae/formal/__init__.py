from amaranth import ClockSignal, Elaboratable, Module, ResetSignal
from amaranth.asserts import Assert, Assume, Cover
from rainhdx import FormalHelper

from ..rtl import Top as RtlTop


class Top(FormalHelper, Elaboratable):
    def __init__(self):
        super().__init__()

        self.sync_clk = ClockSignal("sync")
        self.sync_rst = ResetSignal("sync")

    @property
    def ports(self):
        return [
            self.sync_clk,
            self.sync_rst,
        ]

    def elaborate(self, platform):
        m = Module()

        sync_clk = ClockSignal("sync")
        sync_rst = ResetSignal("sync")

        sync_clk_past = self.past(m, sync_clk, cycles=1)
        m.d.comb += Assume(sync_clk == ~sync_clk_past)
        m.d.comb += Assume(~sync_rst)

        m.submodules.top = top = RtlTop()

        # pc should always be divisible by 4
        m.d.comb += Assert(top.pc[:2] == 0)

        m.d.comb += Cover(top.pc == 0)
        m.d.comb += Cover(top.pc == 4)
        m.d.comb += Cover(top.pc == 8)
        m.d.comb += Cover(top.pc == 12)

        return m
