import os
import rainhdx
import subprocess
from amaranth_boards.icebreaker import ICEBreakerPlatform

from . import rtl, formal

__all__ = ["Sae", "icebreaker"]


class Sae(rainhdx.Project):
    name = "sae"
    top = rtl.Top
    formal_top = formal.Top


class icebreaker(ICEBreakerPlatform, rainhdx.Platform):
    pass
