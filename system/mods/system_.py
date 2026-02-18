import inspect
import asyncio
from system.mods.helper import _PathProxy, _InfoProxy, _ListProxy, _normalize_path, _get_entity
from system.mods.message import Message
from system.mods.handler import Handler, register_handler
from system.mods.component import include_method

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
    def __init__(self, name="system", desc="", attach=None, allow=None):
        self.name = name
        self.desc = desc
        self._components = []
        self._handlers = {}
        self._components_by_prefix = {}
        
        # Local attachments and allowances
        self._local_handlers = {}
        self._allowed_components = set()

        from system.mods.builder import HandlerFactory
        if attach:
            for item in attach:
                if isinstance(item, HandlerFactory):
                    # This is a bit tricky since we need a name - we'll generate one
                    # In practice, you'd want to pass named attachments
                    name = f"handler_{len(self._local_handlers)}"
                    self._attach_local(name=name, handler=item)
                elif hasattr(item, 'name'):
                    self._attach_local(name=item.name, handler=item)

        # Process local allowances
        if allow:
            for component_type in allow:
                self._allow_local(component_type)

        # Remove the old get proxy since we're implementing new functionality
        # self.get = _GetProxy(self)  # Remove this line
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

    def _attach_local(self, *, name: str, handler, kind=None, desc=None, validators=()):
        """Local version of attach for this instance only"""
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
        self._local_handlers[name] = derived
        setattr(self, name, derived)
        return derived

    def _allow_local(self, component_type) -> None:
        """Local version of allow for this instance only"""
        self._allowed_components.add(component_type)

    def __call__(self, *args, **kwargs):
        # If called with handler parameter, delegate to call method
        if 'handler' in kwargs:
            handler_path = kwargs.pop('handler')
            return self.call(handler_path, **kwargs)
        
        # If called with positional args and keyword args, it means we want to call the handler
        if args and len(args) == 1 and kwargs:
            path = args[0]
            normalized_path = _normalize_path(path)
            # Get the handler and call it with the provided kwargs
            handler_func = _get_entity(self, normalized_path)
            return handler_func(**kwargs)
        
        # If called with only positional args, behave like get
        if args:
            path = args[0]
            normalized_path = _normalize_path(path)
            return _get_entity(self, normalized_path)
        
        raise TypeError("System must be called with either a path or handler parameter")

    def __getitem__(self, path):
        """Enable system['/some/path'] syntax"""
        normalized_path = _normalize_path(path)
        return _get_entity(self, normalized_path)

    def __getattr__(self, item: str) -> _PathProxy:
        if item.startswith("_"):
            raise AttributeError(item)

        # Check if this is a local handler
        if item in self._local_handlers:
            return self._local_handlers[item]

        # Remove check for "get" since we're removing it
        # if item in ("get", "list", "info"):
        #     raise AttributeError(item)

        prefix = (item,)
        if not any(h.path[:1] == prefix for h in self._handlers.values()):
            raise AttributeError(
                f"No handler path starting with {prefix!r} in system '{self.name}'"
            )

        return _PathProxy(self, prefix)

    def include(self, component, prefix):
        # Check both global and local allowances
        cls = self.__class__
        global_allowed = getattr(cls, "_allowed_components", set())
        local_allowed = getattr(self, "_allowed_components", set())
        allowed = global_allowed | local_allowed
        comp_cls = component.__class__

        if not any(issubclass(comp_cls, a) for a in allowed):
            raise TypeError(
                f"{cls.__name__} is not allowed to include components of type "
                f"{comp_cls.__name__}. Call {cls.__name__}.allow({comp_cls.__name__}) or "
                f"pass allow=[{comp_cls.__name__}] to the constructor."
            )
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

    @classmethod
    def allow(cls, component_type) -> None:
        allowed = getattr(cls, "_allowed_components", None)
        if allowed is None:
            allowed = set()
        allowed.add(component_type)
        cls._allowed_components = allowed

    def get_handler_info(self, path):
        """Helper method to get handler info by path"""
        normalized_path = _normalize_path(path)
        return self._handlers.get(normalized_path)

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
