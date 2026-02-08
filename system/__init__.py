from importlib import import_module as __import__
from typing import TYPE_CHECKING as __lsp__

__all__ = [
    "Data", "Status", "Message", "message",
    "Handler",
    "System",
    "Component",
    "new"
]

__lazy__ = {
    "Data":      ("system.mods.message", "Data"),
    "Status":    ("system.mods.message", "Status"),
    "Message":   ("system.mods.message", "Message"),
    "message":   ("system.mods.message", "message"),
    "Handler":   ("system.mods.handler", "Handler"),
    "System":    ("system.mods.system_", "System"),
    "Component": ("system.mods.component", "Component"),
    "new":       ("system.mods.builder", "new")
}

def __getattr__(name):
    try:
        module_name, attr_name = __lazy__[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    module = __import__(module_name)
    attr = getattr(module, attr_name)
    globals()[name] = attr
    return attr


def __dir__():
    return sorted(set(globals().keys()) | set(__all__))

if __lsp__:
    from system.mods.message   import Data, Status, Message, message
    from system.mods.handler   import Handler
    from system.mods.system_   import System
    from system.mods.component import Component
    from system.mods.builder   import new
