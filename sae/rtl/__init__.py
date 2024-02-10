import png
from amaranth import (
    Module,
    Memory,
    Signal,
    Elaboratable,
)
from amaranth.build import Resource, Pins, Attrs, PinsN

__all__ = ["Top"]


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        self.mem = None

        return m
