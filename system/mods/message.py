from typed import (
    typed,
    model,
    Str,
    Bool,
    Int,
    Maybe,
    Bytes,
    Enum,
    Union,
    Dict,
    List,
    Set,
    Typed,
    Lazy,
    Any
)
from typed.types import Callable

Data = Union(Dict, List, Set, Str, Int, Bytes)
Status = Enum(Str, "success", "failure")

@typed
def message(message: Str="", handler: Maybe(Callable)=None, **kwargs: Dict(Str)) -> Any:
    if not kwargs:
        full_message = message
    else:
        full_message = message.rstrip(":") + ":"
        parts = [f"{k}={v!r}" for k, v in kwargs.items()]
        full_message += " " + ", ".join(parts)
        full_message += "."

    if handler is None:
        return full_message

    if isinstance(handler, type) and issubclass(handler, BaseException):
        raise handler(full_message)

    handler(full_message)
    return None

@model
class Message:
    """
    Generic message type:
      - message: human-readable string
      - data:    arbitrary structured data
      - success: whether the operation succeeded
      - code:    numeric code (HTTP code, error code, etc.)
    """
    message: Maybe(Str)=None
    data:    Maybe(Data)=None
    success: Maybe(Bool)=None
    code:    Maybe(Int)=None

Message.__display__ = 'Message'

class Propagate(Exception):
    def __init__(self, msg: Message):
        self.msg = msg

class propagate:
    @typed
    def failure(msg: Message) -> Message:
        if not msg.success:
            raise Propagate(msg)
        return msg

    @typed
    def success(msg: Message) -> Message:
        if msg.success:
            raise Propagate(msg)
        return msg

def _propagator(t):
    import types

    if getattr(t, "is_propagator", False):
        return t

    orig_call = t.__call__

    def wrapped_call(self, *args, **kwargs):
        try:
            return orig_call(*args, **kwargs)
        except Propagate as exc:
            return exc.msg

    t.__call__ = types.MethodType(wrapped_call, t)
    t.is_propagator = True
    return t


def propagator(f=None, **kwargs):
    def decorator(obj):
        if obj in Typed or obj in Lazy:
            t = obj
        else:
            t = typed(obj, **kwargs)
        return _propagator(t)

    if f is not None and callable(f):
        return decorator(f)
    return decorator
