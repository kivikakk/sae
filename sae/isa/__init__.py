import inspect
from functools import wraps

from amaranth.lib.enum import IntEnum, nonmember

from .ilayout import ILayout, xfrm

__all__ = ["ISA", "fn_insn", "RegisterSpecifier", "ILayout", "xfrm"]


class ISA:
    def __init_subclass__(cls):
        cls.layouts = []
        cls.insns = []
        for name in [*cls.__dict__]:
            obj = cls.__dict__[name]
            if getattr(obj, "_needs_name", False):
                del obj._needs_name
                obj.__name__ = name
                obj.__fullname__ = f"{cls.__module__}.{cls.__qualname__}.{name}"
            if getattr(obj, "_needs_finalise", False):
                del obj._needs_finalise
                obj.finalise(cls)
            if type(obj) is type and issubclass(obj, ILayout) and hasattr(obj, "layout"):
                cls.layouts.append(obj)
            if isinstance(obj, ILayout): # XXX Insufficient — what of fn_insn-generated?
                cls.insns.append(obj)
        super().__init_subclass__()


def fn_insn(inner):
    class InsnHelper:
        def __init__(self):
            self._needs_finalise = True

        def finalise(self, isa):
            self.isa = isa
            parameters = inspect.signature(inner).parameters
            # Don't take cls along for the ride.
            self.asm_args = [p.name for p in parameters.values() if p.kind == p.KEYWORD_ONLY]

        @wraps(inner)
        def value(self, **kwargs):
            return inner(self.isa, **kwargs)

    return InsnHelper()


def RegisterSpecifier(size, names):
    count = 2**size
    if len(names) < count:
        raise ValueError(
            f"Register naming is inadequate (named {len(names)}/{count}).")
    elif len(names) > count:
        raise ValueError(
            f"Register naming is excessive (named {len(names)}/{count}).")

    members = {}
    mappings = {}
    aliases_ = {}
    for i, ax in enumerate(names):
        match ax:
            case [primary, *rest]:
                members[primary.upper()] = i
                for a in rest:
                    mappings[a.upper()] = primary.upper()
                aliases_[primary.upper()] = [n.upper() for n in ax]
            case str():
                members[ax.upper()] = i
            case _:
                raise TypeError(f"Unknown name specifier {ax!r}.")

    class Register(IntEnum, shape=size):
        locals().update(members)

        _mappings = nonmember(mappings)
        _aliases = nonmember(aliases_)
        _needs_name = nonmember(True)

        @classmethod
        def _missing_(cls, value):
            value = value.upper()
            try:
                return cls[cls._mappings[value]]
            except KeyError:
                return cls[value]

        @nonmember
        @property
        def aliases(self):
            return self._aliases[self._name_]

    return Register
