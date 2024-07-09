import inspect
from functools import reduce, wraps

from amaranth import Shape
from amaranth.lib.data import StructLayout

__all__ = ["ILayout", "xfrm"]


class ILayout:
    defaults = {}

    def __init_subclass__(cls, len=None):
        if len is not None:
            cls.len = len

        if hasattr(cls, "layout"):
            # Not a base class.
            cls._needs_name = True
            cls._needs_finalise = True
            if getattr(cls, "len", None) is None:
                raise ValueError(
                    f"'{cls.__module__}.{cls.__qualname__}' missing len, "
                    f"and no default given.")

        super().__init_subclass__()

    @classmethod
    def resolve(cls, name, *args, **kwargs):
        raise ValueError(
            f"Field specifier {name!r} not registered, and "
            f"no 'resolve' implementation available.")

    @classmethod
    def finalise(cls, isa):
        assert hasattr(cls, "layout"), "finalising a non-leaf ILayout"
        if not isinstance(cls.layout, tuple):
            raise TypeError(
                f"Expected tuple for '{cls.__fullname__}', "
                f"not {type(cls.layout).__name__}.")

        # Assemble defining context, used when evaluating annotations.
        context = {}
        for klass in reversed(isa.mro()):
            context.update({k: v for k, v in klass.__dict__.items() if not k.startswith("_")})

        # Assemble annotations of all ILayout subclasses in our hierarchy.
        mro = list(reversed(cls.mro()))
        annotations = {}
        for klass in mro[mro.index(ILayout) + 1 :]:
            annotations.update(inspect.get_annotations(klass, locals=context, eval_str=True))

        # Evaluate fields elements' shapes: either `(name, shape)` tuples
        # (fully-specified), or `name` where it matches an annotation (which
        # defines its shape). If there's no match, try the class's `resolve`
        # method.
        fields = {}
        field_ranges = {}
        consumed = 0
        for i, elem in enumerate(cls.layout):
            if isinstance(elem, tuple) and len(elem) == 2:
                fields[elem[0]] = elem[1]
                elem = elem[0]
            elif not isinstance(elem, str):
                raise TypeError(
                    f"Unknown field specifier {elem!r} in layout of '{cls.__fullname__}'.")
            elif ty := annotations.get(elem, None):
                fields[elem] = ty
            else:
                after = cls.layout[i + 1 :]
                remlen = cls.len - consumed
                fields[elem] = cls.resolve(elem, after=after, remlen=remlen)

            width = Shape.cast(fields[elem]).width
            field_ranges[elem] = (consumed, consumed + width)
            consumed += width

        if consumed < cls.len:
            raise ValueError(
                f"Layout components are inadequate (fills {consumed}/{cls.len}).")
        elif consumed > cls.len:
            raise ValueError(
                f"Layout components are excessive (fills {consumed}/{cls.len}).")

        cls.fields = fields
        cls.field_ranges = field_ranges

        cls.shape = StructLayout(fields)
        cls.shape.__name__ = cls.__name__

        cls.defaults = cls.resolve_values(cls.defaults)

    @classmethod
    def resolve_values(cls, values):
        return {name: cls.resolve_value(name, value) for name, value in values.items()}

    @classmethod
    def resolve_value(cls, name, value):
        match value:
            case int():
                return value
            case str():
                try:
                    field = cls.fields[name]
                    # Try item access, then calling (e.g. for Enum _missing_).
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
                    f"unhandled type resolving '{cls.__fullname__}': "
                    f"{name!r}={value!r} (fields={cls.fields!r})")

    def __init__(self, **kwargs):
        if not hasattr(self, "layout"):
            raise TypeError(
                f"'{type(self).__module__}.{type(self).__qualname__}' "
                f"called, but it's layoutless.")

        self.kwargs = kwargs
        self._needs_name = True
        self.__fullname__ = f"{type(self).__module__}.{type(self).__qualname__} child"
        self.xfrms = []

        # "valid_args" are those that can be specified in a __call__.
        self.valid_args = list(self.layout)
        self.validate_kwargs(kwargs)

        # "asm_args" are those that can be specified in value().
        self.asm_args = list(self.layout)
        for arg in [*self.defaults, *kwargs]:
            try:
                self.asm_args.remove(arg)
            except ValueError:
                pass

    def __repr__(self):
        return f"<{self.__fullname__}>"

    def validate_kwargs(self, kwargs):
        for name in kwargs:
            if name not in self.valid_args:
                raise ValueError(f"'{self.__fullname__}' given invalid argument {name!r}.")

    def __call__(self, **kwargs):
        self.validate_kwargs(kwargs)

        clone = self.clone()
        clone.kwargs.update(kwargs)
        for arg in kwargs:
            try:
                clone.asm_args.remove(arg)
            except ValueError:
                pass
        return clone

    def value(self, **kwargs):
        args = self.args_for(**kwargs)
        if len(args) < len(self.layout):
            missing = list(self.layout)
            for name in args:
                missing.remove(name)
            raise TypeError(
                f"'{self.__fullname__}' called without supplying "
                f"values for arguments: {missing!r}.")

        return self.shape.const(args).as_value().value

    def match_value(self, inp):
        known = self.args_for()

        rem = list(self.layout)
        for elem, value in known.items():
            start, end = self.field_ranges[elem]
            matching = (inp >> start) & (2 ** (end - start) - 1)
            if matching != value:
                return None
            rem.remove(elem)

        kwargs = {}
        for elem in rem:
            start, end = self.field_ranges[elem]
            matching = (inp >> start) & (2 ** (end - start) - 1)
            kwargs[elem] = matching

        return reduce(lambda kwargs, xfn: xfn.reverse(kwargs), self.xfrms, kwargs)

    def args_for(self, **kwargs):
        combined = reduce(lambda kwargs, xfn: xfn(kwargs), self.xfrms, self.kwargs | kwargs)
        for name in combined:
            if name not in self.layout:
                raise ValueError(
                    f"'{self.__fullname__}' called with argument "
                    f"{name!r}, which is not part of its layout.")
            if name in kwargs and (
                name in self.defaults
                or name in self.kwargs
            ):
                raise ValueError(
                    f"{name!r} is already defined for '{self.__fullname__}' "
                    f"and cannot be overridden.")

        return {
            **self.defaults,
            **self.resolve_values(combined),
        }

    def clone(self):
        clone = type(self)(**self.kwargs.copy())
        clone.xfrms = self.xfrms.copy()
        clone.valid_args = self.valid_args.copy()
        clone.asm_args = self.asm_args.copy()
        return clone

    def xfrm(self, xfn, **kwarg_overrides):
        clone = self.clone()

        if inspect.isfunction(xfn):
            xfn_sig = inspect.signature(xfn, eval_str=True)
            # Return annotations can be generated programmatically (see imm_xfrm).
            return_annotation = getattr(xfn, "return_annotation", xfn_sig.return_annotation)
            parameters = xfn_sig.parameters

            # All parameters become valid __call__ args. Required parameters become value() args.
            for name, p in parameters.items():
                clone.valid_args.append(name)
                if p.default is xfn_sig.empty:
                    clone.asm_args.append(name)

            # Outputs named in the annotation are no longer inputs.
            assert return_annotation is not xfn_sig.empty, f"no return annotation on {xfn}"
            for name in return_annotation:
                clone.valid_args.remove(name)
                clone.asm_args.remove(name)

            @wraps(xfn)
            def pipe(kwargs):
                args = {}
                for name, p in parameters.items():
                    if p.default is p.empty:
                        try:
                            args[name] = kwargs.pop(name)
                        except KeyError:
                            return kwargs
                    else:
                        # Default value (in function signature) may be overridden
                        # by kwarg_overrides.
                        args[name] = kwargs.pop(
                            name, kwarg_overrides.get(name, p.default))
                kwargs.update(xfn(**{**kwarg_overrides, **args}))
                return kwargs

            def pipe_reverse(kwargs):
                if rev := getattr(xfn, "reverse", None):
                    return rev(**kwargs)
                return kwargs

            pipe.reverse = pipe_reverse

            clone.xfrms.insert(0, pipe)
        elif issubclass(xfn, ITransform):
            xfrm = xfn(self, **kwarg_overrides)
            for name in xfrm.inputs:
                clone.valid_args.append(name)
                clone.asm_args.append(name)
            for name in xfrm.layout:
                clone.valid_args.remove(name)
                clone.asm_args.remove(name)
            def pipe(kwargs):
                try:
                    args = {k: kwargs.pop(k) for k in xfrm.inputs}
                except KeyError:
                    return kwargs
                return {**kwargs, **xfrm.inputs_to_layout(**args)}
            def reverse(kwargs):
                args = {k: kwargs.pop(k) for k in xfrm.layout}
                return {**kwargs, **xfrm.layout_to_inputs(**args)}
            pipe.reverse = reverse
            clone.xfrms.insert(0, pipe)
        else:
            assert False, xfn

        return clone


class ITransform:
    ilcls: type[ILayout]
    inputs: list[str]
    layout: list[str]

    def __init__(self, ilcls: type[ILayout], *, inputs: list[str], layout: list[str]):
        self.ilcls = ilcls
        self.inputs = inputs
        self.layout = layout

    def inputs_to_layout(self, **kwargs):
        "Takes each of `inputs` (only) as kwargs, returns a dict containing each of `layout`."
        raise NotImplementedError

    def layout_to_inputs(self, **kwargs):
        "Reverses `inputs_to_layout`."
        raise NotImplementedError


def xfrm(return_annotation=None):
    # HACK: allow @xfrm as shorthand for @xfrm().
    if inspect.isfunction(return_annotation):
        return xfrm()(return_annotation)

    def wrapper(inner):
        if return_annotation is not None:
            inner.return_annotation = tuple(return_annotation)

        def reverse_fn(reverse):
            inner.reverse = reverse

        inner.reverse_fn = reverse_fn

        return inner

    return wrapper
