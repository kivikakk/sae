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


class plats:
    class test(rainhdx.Platform):
        simulation = True

        @property
        def default_clk_frequency(self):
            return 1e6

    class formal(test):
        pass
