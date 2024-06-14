import niar

from . import rtl
from .targets import icebreaker

__all__ = ["Sae"]


class Sae(niar.Project):
    name = "sae"
    top = rtl.Top
    targets = [icebreaker]
