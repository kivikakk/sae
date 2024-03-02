import inspect

from amaranth import Shape
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import IntEnum, nonmember

"""

What is an ISA?

It encompasses:

* Instruction layouts.
  * Each layout has a common field, the opcode.
* Instructions encoded using those layouts.

"""


"""

TODO

* We could also use __init_subclass__ to bind registers to the ISA they were
  created in!

"""


class ISA:
    def __init_subclass__(cls):
        for name, obj in cls.__dict__.items():
            if getattr(obj, "_needs_renamed", False):
                del obj._needs_renamed
                obj.__name__ = name
            if getattr(obj, "_needs_finalised", False):
                obj.finalise(cls)

    @staticmethod
    def RegisterSpecifier(size, names):
        count = 2**size
        if len(names) < count:
            raise ValueError(
                f"Register naming is inadequate (named {len(names)}/{count})."
            )
        elif len(names) > count:
            raise ValueError(
                f"Register naming is excessive (named {len(names)}/{count})."
            )

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
            _needs_renamed = nonmember(True)

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

    class ILayouts:
        _needs_finalised = True

        def __init_subclass__(cls, *, len):
            cls.len = len

        @classmethod
        def finalise(cls, isa):
            annotations = inspect.get_annotations(
                cls, locals=isa.__dict__, eval_str=True
            )
            for name, elems in cls.__dict__.items():
                if name[0] == name[0].lower():
                    continue
                if isinstance(elems, str):
                    # X = ("a") # oops!
                    elems = (elems,)
                il = ISA.ILayout(name, annotations, cls)
                for elem in elems:
                    il.append(elem)
                setattr(cls, name, il.finalise())

    class ILayout:
        def __init__(self, name, annotations, ils):
            self.name = name
            self.annotations = annotations
            self.len = ils.len

            self.after = None
            self.remlen = None

            self._ils = ils
            self._elems = []

        def append(self, name):
            self._elems.append(name)

        def finalise(self):
            self.fields = {}
            consumed = 0
            for i, elem in enumerate(self._elems):
                if isinstance(elem, tuple) and len(elem) == 2:
                    self.fields[elem[0]] = elem[1]
                    elem = elem[0]
                elif not isinstance(elem, str):
                    raise TypeError(f"Unknown field specifier {elem!r}.")
                elif ty := self.annotations.get(elem, None):
                    self.fields[elem] = ty
                elif hasattr(self._ils, "resolve"):
                    self.after = self._elems[i + 1 :]
                    self.remlen = self.len - consumed
                    self.fields[elem] = self._ils.resolve(self, elem)
                else:
                    raise ValueError(
                        f"Field specifier {elem!r} not registered, and no default type "
                        f"function given."
                    )

                consumed += Shape.cast(self.fields[elem]).width

            if consumed < self.len:
                raise ValueError(
                    f"Layout components are inadequate (fills {consumed}/{self.len})."
                )
            elif consumed > self.len:
                raise ValueError(
                    f"Layout components are excessive (fills {consumed}/{self.len})."
                )

            IL = StructLayout(self.fields)
            IL.__name__ = self.name
            return IL
