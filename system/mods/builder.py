from __future__ import annotations
from functools import wraps, partial
from typed import name
from system.mods.system_ import System, SYSTEM
from system.mods.component import Component, COMPONENT, include_method
from system.mods.handler import handler, HandlerInfo, register_handler, Handler
from system.mods.message import Message, message as _message, _plain_message
from system.mods.helper import _normalize_path

class _ClassOnly:
    def __init__(self, func):
        self._func = func

    def __get__(self, instance, owner):
        if instance is not None:
            raise AttributeError(
                f"'{owner.__name__}' object has no attribute "
                f"'{self._func.__name__}' (class-only)"
            )
        return self._func.__get__(owner, owner)

def class_only(func):
    return _ClassOnly(func)

_UNSET = object()

class HandlerFactory:
    def __init__(self, *, msg_type=Message, name="handler", kind=None, validators=(), desc=None, base_kwargs=None) -> None:
        self.msg_type = msg_type
        self.name = name
        self.kind = kind or name
        self.validators = tuple(validators)
        self.desc = desc
        self.base_kwargs = dict(base_kwargs or {})

    def with_validators(self, *validators, name=None, kind=None, desc=None):
        return HandlerFactory(
            msg_type=self.msg_type,
            name=name or self.name,
            kind=kind or self.kind,
            validators=self.validators + tuple(validators),
            desc=desc if desc is not None else self.desc,
            base_kwargs=self.base_kwargs
        )

    def __call__(self, f=None, **kwargs):
        all_kwargs = {**self.base_kwargs, **kwargs}

        def _decorate(func):
            orig = func

            if self.validators:
                @wraps(orig)
                def validated(*args, **kw):
                    for v in self.validators:
                        v(*args, **kw)
                    return orig(*args, **kw)

                validated.__annotations__ = getattr(orig, "__annotations__", {}).copy()
                target = validated
            else:
                target = orig

            ann = getattr(target, "__annotations__", {})
            if "return" not in ann and self.msg_type is not None:
                ann = dict(ann)
                ann["return"] = self.msg_type
                target.__annotations__ = ann

            h = handler(target, **all_kwargs)

            cod = getattr(h, "cod", None)
            if self.msg_type is not None and cod is not None:
                try:
                    ok = cod <= self.msg_type
                except TypeError:
                    ok = False
                if not ok:
                    raise TypeError(
                        "Codomain mismatch in handler:\n"
                        f"  ==> '{orig.__name__}': should return a subtype of '{name(self.msg_type)}'.\n"
                        f"      [expected_type] subtype of '{name(self.msg_type)}'\n"
                        f"      [received_type] '{name(cod)}'"
                    )

            h.action_kind = self.kind
            h.action_factory = self
            h.validators = self.validators
            h.action_desc = self.desc

            return h

        if f is not None and callable(f):
            return _decorate(f)

        _decorate.call = self.call
        _decorate.data = self.data
        _decorate.success = self.success
        _decorate.failure = self.failure
        _decorate.propagate = self.propagate

        return _decorate

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return partial(self._registrar, instance)

    def _registrar(self, owner_obj, path, name= None, **meta):
        rel_path = _normalize_path(path)

        def decorator(func):
            h = self(func)
            h_name = name or getattr(func, "__name__", "handler")

            meta_full = dict(meta)
            meta_full.setdefault("kind", self.kind)
            if self.validators:
                meta_full.setdefault("validators", self.validators)
            if self.desc is not None:
                meta_full.setdefault("desc", self.desc)

            if hasattr(owner_obj, "_local_handlers") and not isinstance(owner_obj, System):
                entry = HandlerInfo(
                    path=rel_path,
                    name=h_name,
                    func=h,
                    owner=owner_obj,
                    meta=meta_full,
                )
                owner_obj._local_handlers[rel_path] = entry

                if not hasattr(owner_obj, h_name):
                    setattr(owner_obj, h_name, h)

                system = getattr(owner_obj, "system", None)
                if system is not None:
                    abs_path = owner_obj.prefix + rel_path
                    register_handler(
                        system,
                        path=abs_path,
                        name=entry.name,
                        func=h,
                        owner=owner_obj,
                        meta=entry.meta,
                    )

            else:
                abs_path = rel_path
                register_handler(
                    owner_obj,
                    path=abs_path,
                    name=h_name,
                    func=h,
                    owner=owner_obj,
                    meta=meta_full,
                )

                if abs_path:
                    last_seg = abs_path[-1]
                    if last_seg and not hasattr(owner_obj, last_seg):
                        setattr(owner_obj, last_seg, h)

            return h
        return decorator

    def call(self, *args, **kwargs):
        return handler.call(*args, **kwargs)

    def data(self, *args, **kwargs):
        return handler.data(*args, **kwargs)

    def success(self, obj=_UNSET, message=_UNSET, data=_UNSET, code=_UNSET, **kwargs):
        if obj is not _UNSET:
            if not isinstance(obj, Message):
                raise TypeError("obj must be an instance of Message")
            init = _plain_message(obj)
        else:
            init = {}

        init["status"] = "success"
        init["success"] = True

        if message is not _UNSET:
            init["message"] = _message(message=message, **kwargs)
        if data is not _UNSET:
            init["data"] = data

        if code is not _UNSET:
            init["code"] = code
        else:
            if "code" in init and init["code"] is None:
                init.pop("code")

        return self.msg_type(**init)

    def failure(self, obj=_UNSET, message=_UNSET, data=_UNSET, code=_UNSET, **kwargs):
        if obj is not _UNSET:
            if not isinstance(obj, Message):
                raise TypeError("obj must be an instance of Message")
            init = _plain_message(obj)
        else:
            init = {}

        init["status"] = "failure"
        init["success"] = False

        if message is not _UNSET:
            init["message"] = _message(message=message, **kwargs)
        if data is not _UNSET:
            init["data"] = data

        if code is not _UNSET:
            init["code"] = code
        else:
            if "code" in init and init["code"] is None:
                init.pop("code")

        return self.msg_type(**init)

    def propagate(self, obj, *args, **kwargs):
        if not isinstance(obj, Message):
            raise TypeError("obj must be an instance of Message")

        if obj.success is True:
            return self.success(obj, *args, **kwargs)

        if obj.success is False:
            return self.failure(obj, *args, **kwargs)

        init = _plain_message(obj)
        if kwargs:
            init.update(kwargs)

        return self.msg_type(**init)

def new_handler(message=Message, *, validators=(), name="handler", kind=None, desc=None, **kwargs):
    return Handler(
        message,
        validators=validators,
        name=name,
        kind=kind,
        desc=desc,
        **kwargs,
    )

def new_system(name, desc="", *bases):
    if not bases:
        bases = (System,)
    else:
        if not any(issubclass(b, System) for b in bases):
            bases = bases + (System,)

    @class_only
    def attach(
        cls,
        *,
        name: str,
        kind = None,
        desc = None,
        handler: HandlerFactory,
        validators = (),
    ) -> HandlerFactory:
        if not isinstance(handler, HandlerFactory):
            raise TypeError("handler must be a HandlerFactory produced by new_handler()")

        derived = handler.with_validators(
            *validators,
            name=name,
            kind=(kind or name),
            desc=desc,
        )
        setattr(cls, name, derived)
        return derived

    @class_only
    def allow(cls, component_type) -> None:
        allowed = getattr(cls, "_allowed_components", None)
        if allowed is None:
            allowed = set()
        allowed.add(component_type)
        cls._allowed_components = allowed


    def include(self, component: Component, prefix=None):
        cls = self.__class__
        allowed = getattr(cls, "_allowed_components", set())
        comp_cls = component.__class__

        if not any(issubclass(comp_cls, a) for a in allowed):
            raise TypeError(
                f"{cls.__name__} is not allowed to include components of type "
                f"{comp_cls.__name__}. Call {cls.__name__}.allow({comp_cls.__name__}) first."
            )
        return include_method(self, component, prefix)

    namespace = {
        "__module__": System.__module__,
        "__doc__": desc or "",
        "_allowed_components": set(),
        "attach": attach,
        "allow": allow,
        "include": include,
    }

    cls = SYSTEM(name, bases, namespace)
    return cls

def new_component(name="Component", desc="", *bases):
    if not bases:
        bases = (Component,)
    else:
        if not any(issubclass(b, Component) for b in bases):
            bases = bases + (Component,)

    @class_only
    def attach(
        cls,
        *,
        name: str,
        kind = None,
        desc = None,
        handler: HandlerFactory,
        validators = (),
    ) -> HandlerFactory:
        if not isinstance(handler, HandlerFactory):
            raise TypeError("handler must be a HandlerFactory produced by new_handler()")

        derived = handler.with_validators(
            *validators,
            name=name,
            kind=(kind or name),
            desc=desc,
        )
        setattr(cls, name, derived)
        return derived

    @class_only
    def allow(cls, component_type) -> None:
        allowed = getattr(cls, "_allowed_components", None)
        if allowed is None:
            allowed = set()
        allowed.add(component_type)
        cls._allowed_components = allowed

    def include_checked(self, component: Component, prefix=None):
        cls = self.__class__
        allowed = getattr(cls, "_allowed_components", set())
        comp_cls = component.__class__

        if not (comp_cls is cls or issubclass(comp_cls, cls)):
            if not any(issubclass(comp_cls, a) for a in allowed):
                raise TypeError(
                    f"{cls.__name__} is not allowed to include components of type "
                    f"{comp_cls.__name__}. Call {cls.__name__}.allow({comp_cls.__name__}) first."
                )

        return include_method(self, component, prefix)

    namespace = {
        "__module__": Component.__module__,
        "__doc__": desc or "",
        "_allowed_components": set(),
        "attach": attach,
        "allow": allow,
        "include": include_checked,
    }

    cls = COMPONENT(name, bases, namespace)
    cls._allowed_components = {cls}
    return cls

class new:
    handler = new_handler
    system = new_system
    component = new_component
