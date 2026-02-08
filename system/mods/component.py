from typed import Maybe, Str
from system.mods.helper import _normalize_path, _InfoProxy
from system.mods.handler import (
    Handler,
    HandlerInfo,
    register_handler,
)

class COMPONENT(type):
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

            if value in Handler or getattr(value, "is_handler", False):
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

def include_method(self, component, prefix=None):
    def _attach(component, system, absolute_prefix=None):
        if component.system is not None and component.system is not system:
            raise ValueError("Component is already attached to a different System")

        component.system = system
        if absolute_prefix is not None:
            component.prefix = _normalize_path(absolute_prefix)

        if hasattr(system, "_components_by_prefix"):
            key = tuple(component.prefix)
            system._components_by_prefix[key] = component

        for rel_path, info in component._local_handlers.items():
            abs_path = component.prefix + rel_path
            register_handler(
                system,
                path=abs_path,
                name=info.name,
                func=info.func,
                owner=component,
                meta=info.meta,
            )

        for child in component._components:
            child_abs_prefix = component.prefix + child.prefix
            _attach(child, system, absolute_prefix=child_abs_prefix)

    extra = _normalize_path(prefix)
    component.prefix = extra + component.prefix
    self._components.append(component)

    system = getattr(self, "system", None)
    if system is not None:
        abs_prefix = component.prefix if not getattr(self, "prefix", None) else self.prefix + component.prefix
        _attach(component, system, absolute_prefix=abs_prefix)
    else:
        _attach(component, self, absolute_prefix=component.prefix)

        comp_name = getattr(component, "name", None)
        if comp_name:
            if hasattr(self, "get"):
                setattr(self.get, comp_name, component)

            if hasattr(self, "info"):
                setattr(self.info, comp_name, _InfoProxy(self, (comp_name,)))

        if component.name and not hasattr(self, component.name):
            setattr(self, component.name, component)
    return component

class Component:
    def __init__(self, name: Str="component", desc: Str="", prefix: Maybe(Str)=None):
        self.name = name
        self.desc = desc
        self.prefix = _normalize_path(prefix)

        self.system = None
        self._local_handlers = {}
        self._components = []

        for h_name, h in getattr(self.__class__, "__static_handlers__", {}).items():
            rel_path = (h_name,)
            entry = HandlerInfo(
                path=rel_path,
                name=h_name,
                func=h,
                owner=self,
                meta={},
            )
            self._local_handlers[rel_path] = entry

            if not hasattr(self, h_name):
                setattr(self, h_name, h)

        for cname, comp_cls in getattr(self.__class__, "__static_components__", {}).items():
            child = comp_cls()

            if getattr(child, "name", "") in ("", "component"):
                child.name = cname

            self.include_component(child)

    def include(self, component, prefix=None):
        return include_method(self, component, prefix)

    @classmethod
    def attach(
        cls,
        *,
        name: Str,
        kind=None,
        desc: Maybe(Str) = None,
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
