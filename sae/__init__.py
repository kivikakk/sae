import niar

from . import rtl
from .targets import cxxrtl, icebreaker

__all__ = ["Sae"]


class Sae(niar.Project):
    name = "sae"
    top = rtl.Top
    targets = [icebreaker]
    cxxrtl_targets = [cxxrtl]