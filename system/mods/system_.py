from system.mods.helper import _PathProxy, _GetProxy, _InfoProxy, _ListProxy
from system.mods.message import Message
from system.mods.handler import Handler, register_handler
from system.mods.component import include_method

import inspect
import asyncio

class SYSTEM(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        cls = super().__new__(mcls, name, bases, namespace)

        static_handlers = {}
        static_components = {}
        for base in bases:
            static_handlers.update(getattr(base, "__static_handlers__", {}))
            static_components.update(getattr(base, "__static_components__", {}))

        for attr_name, value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if isinstance(value, Handler) or getattr(value, "is_handler", False):
                static_handlers[attr_name] = value
                continue

            if (
                isinstance(value, type)
                and "Component" in globals()
                and issubclass(value, globals()["Component"])
                and value is not globals()["Component"]
            ):
                static_components[attr_name] = value

        cls.__static_handlers__ = static_handlers
        cls.__static_components__ = static_components
        return cls

class System:
    def __init__(self, name="system", desc=""):
        self.name = name
        self.desc = desc
        self._components = []
        self._handlers = {}
        self._components_by_prefix = {}

        self.get = _GetProxy(self)
        self.list = _ListProxy(self)
        self.info = _InfoProxy(self)

        for h_name, h in getattr(self.__class__, "__static_handlers__", {}).items():
            path = (h_name,)
            register_handler(
                self,
                path=path,
                name=h_name,
                func=h,
                owner=self,
                meta={},
            )

            if not hasattr(self, h_name):
                setattr(self, h_name, h)

        for cname, comp_cls in getattr(self.__class__, "__static_components__", {}).items():
            comp = comp_cls()

            if getattr(comp, "name", "") in ("", "component"):
                comp.name = cname

            self.include(comp)

    def __getattr__(self, item: str) -> _PathProxy:
        if item.startswith("_"):
            raise AttributeError(item)

        if item in ("get", "list", "info"):
            raise AttributeError(item)

        prefix = (item,)
        if not any(h.path[:1] == prefix for h in self._handlers.values()):
            raise AttributeError(
                f"No handler path starting with {prefix!r} in system '{self.name}'"
            )

        return _PathProxy(self, prefix)

    def include(self, component, prefix):
        return include_method(self, component, prefix)


    @classmethod
    def attach(
        cls,
        *,
        name: str,
        kind=None,
        desc=None,
        handler,
        validators=(),
    ):
        base = handler
        if not hasattr(base, "with_validators"):
            raise TypeError(
                "handler must be a HandlerFactory produced by new_handler() "
                "or Handler(message=...)."
            )

        derived = base.with_validators(
            *validators,
            name=name,
            kind=(kind or name),
            desc=desc,
        )
        setattr(cls, name, derived)
        return derived

    async def call(self, path, *args, **kwargs) -> Message:
        info = self.get_handler_info(path)
        if info is None:
            raise KeyError(f"No handler registered at path {path!r}")

        result = info.func(*args, **kwargs)

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(result, Message):
            raise TypeError(
                f"Handler at path {path!r} returned {type(result)!r}, "
                "expected a subtype of Message"
            )
        return result

    async def call_many(self, *calls):
        async def _one(p, args, kwargs):
            return await self.call(p, *(args or ()), **(kwargs or {}))

        coros = [
            _one(path, args, kwargs)
            for (path, args, kwargs) in calls
        ]
        return await asyncio.gather(*coros, return_exceptions=False)
