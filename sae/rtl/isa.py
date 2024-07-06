import inspect
from functools import reduce, wraps

from amaranth import Shape
from amaranth.lib.data import StructLayout
from amaranth.lib.enum import IntEnum, nonmember


class ISAMeta(type):
    def __new__(mcls, name, bases, namespace):
        cls = type.__new__(mcls, name, bases, namespace)
        for name in [*cls.__dict__]:
            obj = cls.__dict__[name]
            if getattr(obj, "_needs_named", False):
                del obj._needs_named
                obj.__name__ = name
                obj.__fullname__ = f"{cls.__module__}.{cls.__qualname__}.{name}"
            if getattr(obj, "_needs_finalised", False):
                obj.finalise(cls)
        return cls


class ISA(metaclass=ISAMeta):
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
            _needs_named = nonmember(True)

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

    class ILayoutMeta(type):
        def __new__(mcls, name, bases, namespace, len=None):
            cls = type.__new__(mcls, name, bases, namespace)

            if len is not None:
                cls.len = len

            if not hasattr(cls, "layout"):
                # Base class, not a complete instruction layout.
                return cls
            cls._needs_finalised = True

            if getattr(cls, "len", None) is None:
                raise ValueError(
                    f"'{cls.__fullname__}' missing len, and no default given."
                )

            return cls

        def __call__(cls, *args, **kwargs):
            match args:
                case ():
                    # Can't check for "shape" because this ain't finalised yet.
                    if not hasattr(cls, "layout"):
                        raise TypeError(
                            f"'{cls.__fullname__}' called, but it's layoutless."
                        )

                    return ISA.IThunk(cls, kwargs)

                case [sig]:
                    return cls.shape(sig)

                case _:
                    assert False

        @property
        def __fullname__(self):
            return f"{self.__module__}.{self.__qualname__}"

        def resolve(cls, name, *args, **kwargs):
            raise ValueError(
                f"Field specifier {name!r} not registered, and "
                f"no 'resolve' implementation available."
            )

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
                    f"Expected tuple for '{cls.__fullname__}', "
                    f"not {type(cls.layout).__name__}."
                )

            fields = {}
            consumed = 0
            for i, elem in enumerate(cls.layout):
                if isinstance(elem, tuple) and len(elem) == 2:
                    fields[elem[0]] = elem[1]
                    elem = elem[0]
                elif not isinstance(elem, str):
                    raise TypeError(
                        f"Unknown field specifier {elem!r} in layout of '{cls.__fullname__}'."
                    )
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

            cls._fields = fields

            cls.shape = StructLayout(fields)
            cls.shape.__name__ = cls.__name__

            cls.values = cls.resolve_values(getattr(cls, "values", {}))
            cls.defaults = cls.resolve_values(getattr(cls, "defaults", {}))

            overlap = []
            for name in cls.layout:
                if name in cls.values and name in cls.defaults:
                    overlap.append(name)
            if overlap:
                raise ValueError(
                    f"'{cls.__fullname__}' sets the following in both "
                    f"'values' and 'defaults': {overlap!r}."
                )

        def resolve_value(cls, name, value):
            match value:
                case int():
                    return value
                case str():
                    try:
                        field = cls._fields[name]
                        try:
                            return field[value]
                        except KeyError:
                            return field(value)
                    except Exception as e:
                        raise TypeError(
                            f"Cannot resolve default value for element of '{cls.__fullname__}': "
                            f"{name!r}={value!r}."
                        ) from e
                case _:
                    assert False, (
                        f"unhandled resolving '{cls.__fullname__}': "
                        f"{name!r}={value!r} (fields={cls._fields!r})"
                    )

        def resolve_values(cls, values):
            return {
                name: cls.resolve_value(name, value) for name, value in values.items()
            }

        def xfrm(cls, *args, **kwargs):
            return cls().xfrm(*args, **kwargs)

    class ILayout(metaclass=ILayoutMeta):
        pass

    class IThunk:
        def __init__(self, ilcls, kwargs):
            self.ilcls = ilcls
            self.layout = ilcls.layout
            self.kwargs = kwargs
            self._needs_named = True
            self.__fullname__ = f"{ilcls.__fullname__} child"
            self.xfrms = []

            self.asm_args = list(self.layout)
            for arg in [
                *getattr(self.ilcls, "values", []),
                *getattr(self.ilcls, "defaults", []),
                *kwargs,
            ]:
                try:
                    self.asm_args.remove(arg)
                except ValueError:
                    pass

            for name in kwargs:
                if name not in ilcls.layout:
                    raise ValueError(
                        f"'{ilcls.__fullname__}' called with argument "
                        f"{name!r}, which is not part of its layout."
                    )
                if name in getattr(ilcls, "values", {}):
                    raise ValueError(
                        f"{name!r} is already defined for '{ilcls.__fullname__}' "
                        f"and cannot be overridden."
                    )

        def args_for(self, **kwargs):
            combined = self.do_xfrms(self.kwargs | kwargs)
            for name in combined:
                if name not in self.ilcls.layout:
                    raise ValueError(
                        f"'{self.ilcls.__fullname__}' called with argument "
                        f"{name!r}, which is not part of its IL's layout."
                    )
                if name in kwargs and (
                    name in self.ilcls.values
                    or name in self.ilcls.defaults
                    or name in self.kwargs
                ):
                    raise ValueError(
                        f"{name!r} is already defined for '{self.ilcls.__fullname__}' "
                        f"and cannot be overridden in thunk."
                    )

            return {
                **self.ilcls.values,
                **self.ilcls.defaults,
                **self.ilcls.resolve_values(combined),
            }

        def __call__(self, **kwargs):
            args = self.args_for(**kwargs)
            if len(args) < len(self.ilcls.layout):
                missing = list(self.ilcls.layout)
                for name in args:
                    missing.remove(name)
                raise TypeError(
                    f"'{self.__fullname__}' called without supplying "
                    f"values for arguments: {missing!r}."
                )

            return self.ilcls.shape.const(args).as_value().value

        def clone(self):
            clone = ISA.IThunk(self.ilcls, self.kwargs.copy())
            clone.xfrms = self.xfrms.copy()
            clone.asm_args = self.asm_args.copy()
            return clone

        def partial(self, **kwargs):
            # Note that overwriting defaults is allowed in partial().
            clone = self.clone()
            clone.kwargs.update(kwargs)
            for arg in kwargs:
                try:
                    clone.asm_args.remove(arg)
                except ValueError:
                    pass
            return clone

        def xfrm(self, xfn, **kwarg_defaults):
            clone = self.clone()
            xfn_sig = inspect.signature(xfn, eval_str=True)
            # Return annotations can be generated programmatically (see imm_xfrm).
            return_annotation = getattr(xfn, "return_annotation", xfn_sig.return_annotation)
            parameters = xfn_sig.parameters

            # Any required parameters are now inputs.
            for name, p in parameters.items():
                if p.default is xfn_sig.empty:
                    clone.asm_args.append(name)

            # Outputs named in the annotation are no longer inputs/arguments.
            assert return_annotation is not xfn_sig.empty, f"no return annotation on {xfn}"
            for name in return_annotation:
                clone.asm_args.remove(name)

            @wraps(xfn)
            def pipe(kwargs):
                args = {}
                for name, p in parameters.items():
                    if p.default is p.empty:
                        args[name] = kwargs.pop(name)
                    else:
                        # Default value (in function signature) may be overridden
                        # by kwarg_defaults.
                        args[name] = kwargs.pop(
                            name, kwarg_defaults.get(name, p.default)
                        )
                kwargs.update(xfn(**{**kwarg_defaults, **args}))
                return kwargs

            clone.xfrms.insert(0, pipe)

            return clone

        def do_xfrms(self, kwargs):
            return reduce(lambda kwargs, xfn: xfn(kwargs), self.xfrms, kwargs)
