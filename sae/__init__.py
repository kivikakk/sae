import rainhdx
from amaranth_boards.icebreaker import ICEBreakerPlatform

from . import formal, rtl

__all__ = ["Sae", "icebreaker"]


class Sae(rainhdx.Project):
    name = "sae"
    top = rtl.DeployedTop
    formal_top = formal.Top


class icebreaker(ICEBreakerPlatform, rainhdx.Platform):
    pass


class test(rainhdx.Platform):
    @property
    def default_clk_frequency(self):
        return 1e6


class formal(test):
    pass
