from amaranth import ClockSignal, Elaboratable, Module, ResetSignal
from amaranth.asserts import Assert, Assume, Cover
from rainhdx import FormalHelper

from ..rtl import Hart


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

        sync_clk_past = self.past(m, self.sync_clk, cycles=1)
        m.d.comb += Assume(self.sync_clk == ~sync_clk_past)
        m.d.comb += Assume(~self.sync_rst)

        m.submodules.hart = hart = Hart()

        # pc should always be divisible by 4
        m.d.comb += Assert(hart.pc[:2] == 0)

        m.d.comb += Cover(hart.pc == 0)
        m.d.comb += Cover(hart.pc == 4)
        m.d.comb += Cover(hart.pc == 8)
        m.d.comb += Cover(hart.pc == 12)

        return m
