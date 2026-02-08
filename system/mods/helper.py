import inspect
import asyncio

def _normalize_path(path):
    if path is None:
        return ()
    if isinstance(path, str):
        parts = [p for p in path.strip("/").split("/") if p]
        return tuple(parts)
    out = []
    for p in path:
        if p is None:
            continue
        s = str(p).strip("/")
        if not s:
            continue
        out.extend(s.split("/"))
    return tuple(out)

def _is_direct_child(prefix, path):
    prefix = tuple(prefix)
    path = tuple(path)
    if len(path) != len(prefix) + 1:
        return False
    return path[:len(prefix)] == prefix


def _relative_prefix(child, parent):
    cp = tuple(getattr(child, "prefix", ()))
    pp = tuple(getattr(parent, "prefix", ()))
    if not pp:
        return cp
    if cp[:len(pp)] == pp:
        return cp[len(pp):]
    return cp

def _get_entity(owner, path):
    path = tuple(path)

    if hasattr(owner, "_handlers") and hasattr(owner, "_components_by_prefix"):
        info = owner._handlers.get(path)
        if info is not None:
            return info.func

        comp = owner._components_by_prefix.get(path)
        if comp is not None:
            return comp

        raise KeyError(
            f"No handler or component at path {path!r} in system '{getattr(owner, 'name', 'system')}'"
        )

    if hasattr(owner, "_local_handlers") and hasattr(owner, "_components"):
        if not path:
            return owner

        info = owner._local_handlers.get(path)
        if info is not None:
            return info.func

        for child in owner._components:
            rel = _relative_prefix(child, owner)
            if rel == path:
                return child
            if path[:len(rel)] == rel:
                remainder = path[len(rel):]
                return _get_entity(child, remainder)

        raise KeyError(
            f"No handler or component at path {path!r} under component '{getattr(owner, 'name', 'component')}'"
        )

    raise TypeError("owner must be a System or Component-like object.")


def _list_entities(owner, prefix, kind=None):
    prefix = tuple(prefix)
    kind = (kind or "both").lower()
    results = []

    if hasattr(owner, "_handlers") and hasattr(owner, "_components_by_prefix"):
        if kind in ("handler", "both"):
            for info in owner._handlers.values():
                if _is_direct_child(prefix, info.path):
                    results.append(info)

        if kind in ("component", "both"):
            for cp, comp in owner._components_by_prefix.items():
                if _is_direct_child(prefix, cp):
                    results.append(comp)

        return results

    if hasattr(owner, "_local_handlers") and hasattr(owner, "_components"):
        if kind in ("handler", "both"):
            for rel_path, info in owner._local_handlers.items():
                if _is_direct_child(prefix, rel_path):
                    results.append(info)

        if kind in ("component", "both"):
            for child in owner._components:
                rel = _relative_prefix(child, owner)
                if _is_direct_child(prefix, rel):
                    results.append(child)

        return results
    raise TypeError("owner must be a System or Component-like object.")


def _info_entity(owner, path):
    path = tuple(path)

    if hasattr(owner, "_handlers") and hasattr(owner, "_components_by_prefix"):
        info = owner._handlers.get(path)
        if info is not None:
            return info

        comp = owner._components_by_prefix.get(path)
        if comp is not None:
            return {
                "type": "component",
                "name": getattr(comp, "name", ""),
                "prefix": getattr(comp, "prefix", ()),
                "desc": getattr(comp, "desc", ""),
                "component": comp,
            }

        raise KeyError(
            f"No handler or component at path {path!r} in system '{getattr(owner, 'name', 'system')}'"
        )

    if hasattr(owner, "_local_handlers") and hasattr(owner, "_components"):
        if not path:
            return {
                "type": "component",
                "name": getattr(owner, "name", ""),
                "prefix": getattr(owner, "prefix", ()),
                "desc": getattr(owner, "desc", ""),
                "component": owner,
            }

        info = owner._local_handlers.get(path)
        if info is not None:
            return info

        for child in owner._components:
            rel = _relative_prefix(child, owner)
            if rel == path:
                return {
                    "type": "component",
                    "name": getattr(child, "name", ""),
                    "prefix": getattr(child, "prefix", ()),
                    "desc": getattr(child, "desc", ""),
                    "component": child,
                }
            if path[:len(rel)] == rel:
                remainder = path[len(rel):]
                return _info_entity(child, remainder)

        raise KeyError(
            f"No handler or component at path {path!r} under component '{getattr(owner, 'name', 'component')}'"
        )

    raise TypeError("owner must be a System or Component-like object.")


class _PathProxy:
    def __init__(self, system, path):
        self._system = system
        self._path = path

    def __getattr__(self, item: str):
        if item.startswith("_"):
            raise AttributeError(item)
        new_path = self._path + (item,)

        if not any(h.path[:len(new_path)] == new_path for h in self._system._handlers.values()):
            raise AttributeError(
                f"No handler path starting with {new_path!r} in system '{self._system.name}'"
            )

        return _PathProxy(self._system, new_path)

    def __call__(self, *args, **kwargs):
        coro_or_msg = self._system.call(self._path, *args, **kwargs)

        if inspect.isawaitable(coro_or_msg):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(coro_or_msg)
            else:
                return coro_or_msg

        return coro_or_msg



class _GetProxy:
    def __init__(self, owner, base_path=()):
        self._owner = owner
        self._path = tuple(base_path)

    def __getattr__(self, item: str):
        if item.startswith("_"):
            raise AttributeError(item)

        new_path = self._path + (item,)
        try:
            return _get_entity(self._owner, new_path)
        except KeyError as exc:
            raise AttributeError(str(exc)) from None

    def __call__(self, path):
        rel = _normalize_path(path)
        full = self._path + rel
        return _get_entity(self._owner, full)


class _ListProxy:
    def __init__(self, owner, base_path=()):
        self._owner = owner
        self._path = tuple(base_path)

    def __getattr__(self, item: str):
        if item.startswith("_"):
            raise AttributeError(item)
        new_path = self._path + (item,)
        return _ListProxy(self._owner, new_path)

    def __call__(self, path=None, kind=None):
        rel = _normalize_path(path) if path is not None else ()
        full = self._path + rel
        return _list_entities(self._owner, full, kind=kind)


class _InfoProxy:
    def __init__(self, owner, base_path=()):
        self._owner = owner
        self._path = tuple(base_path)

    def __getattr__(self, item: str):
        if item.startswith("_"):
            raise AttributeError(item)
        new_path = self._path + (item,)
        return _InfoProxy(self._owner, new_path)

    def __call__(self, path=None):
        rel = _normalize_path(path) if path is not None else ()
        full = self._path + rel
        return _info_entity(self._owner, full)
