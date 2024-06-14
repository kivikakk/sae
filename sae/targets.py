from amaranth_boards.icebreaker import ICEBreakerPlatform

__all__ = ["icebreaker", "test"]


class icebreaker(ICEBreakerPlatform):
    pass


class test:
    simulation = True
    default_clk_frequency = 1e6
