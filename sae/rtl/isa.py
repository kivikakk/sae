import inspect

from amaranth import Shape, ShapeCastable
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

* We could also use __init_subclass__ to bind registers/ILs to the ISA they were
  created in!

"""


class ISA:
    def __init_subclass__(cls):
        for name, obj in cls.__dict__.copy().items():
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

    class ILayoutMeta(ShapeCastable, type):
        def as_shape(cls):
            return cls.shape.as_shape()

        def const(cls, obj):
            return cls.shape.const(obj)

        def __call__(cls, obj):
            return cls.shape(obj)

    class ILayout(metaclass=ILayoutMeta):
        def __init_subclass__(cls, *, len=None):
            if len is not None:
                cls.len = len
            if not hasattr(cls, "layout"):
                # Base class, not a complete instruction layout.
                return

            if getattr(cls, "len", None) is None:
                raise ValueError(
                    f"'{cls.__module__}.{cls.__qualname__}' missing len, and no default given."
                )

            cls._needs_finalised = True

        @classmethod
        def resolve(cls, name, *args, **kwargs):
            raise ValueError(
                f"Field specifier {name!r} not registered, and "
                f"no 'resolve' implementation available."
            )

        @classmethod
        def finalise(cls, isa):
            context = {}
            for klass in reversed(isa.mro()):
                context.update(
                    {k: v for k, v in klass.__dict__.items() if not k.startswith("_")}
                )

            mro = list(reversed(cls.mro()))
            annotations = {}
            for klass in mro[mro.index(ISA.ILayout) + 1 :]:
                annotations.update(
                    inspect.get_annotations(klass, locals=context, eval_str=True)
                )

            assert hasattr(cls, "layout"), "finalising a non-leaf ILayout"

            if not isinstance(cls.layout, tuple):
                raise TypeError(
                    f"Expected tuple for '{cls.__module__}.{cls.__qualname__}', "
                    f"not {type(cls.layout).__name__}."
                )

            fields = {}
            consumed = 0
            for i, elem in enumerate(cls.layout):
                if isinstance(elem, tuple) and len(elem) == 2:
                    fields[elem[0]] = elem[1]
                    elem = elem[0]
                elif not isinstance(elem, str):
                    raise TypeError(f"Unknown field specifier {elem!r}.")
                elif ty := annotations.get(elem, None):
                    fields[elem] = ty
                else:
                    after = cls.layout[i + 1 :]
                    remlen = cls.len - consumed
                    fields[elem] = cls.resolve(elem, after=after, remlen=remlen)

                consumed += Shape.cast(fields[elem]).width

            if consumed < cls.len:
                raise ValueError(
                    f"Layout components are inadequate (fills {consumed}/{cls.len})."
                )
            elif consumed > cls.len:
                raise ValueError(
                    f"Layout components are excessive (fills {consumed}/{cls.len})."
                )

            cls.shape = StructLayout(fields)
            cls.shape.__name__ = cls.__name__
