from functools import wraps
from typed import typed, name, Typed, Lazy, model, Tuple, Str, Any, Dict, Maybe, Int
from typed.meta import TYPED
from typed.types import Callable
from system.mods.message import Status, Data, Message, Propagate, propagate as _propagate, message as _message
from system.mods.helper import _normalize_path, _InfoProxy

class HANDLER(TYPED):
    def __instancecheck__(cls, instance):
        if not (instance in Typed or instance in Lazy):
            return False

        if not getattr(instance, "is_propagator", False):
            return False

        if not getattr(instance, "is_handler", False):
            return False

        cod = getattr(instance, "cod", None)
        if cod is None:
            return False
        return cod <= Message

    def __call__(cls, *args, **kwargs):
        if args:
            raise TypeError(
                "Handler(...) as a factory accepts only keyword arguments: "
                "message=..., validators=..., name=..., kind=..., desc=..."
            )

        from system.mods.builder import HandlerFactory

        msg_type   = kwargs.pop("message", Message)
        validators = kwargs.pop("validators", ())
        name       = kwargs.pop("name", "handler")
        kind       = kwargs.pop("kind", None)
        desc       = kwargs.pop("desc", None)

        if kwargs:
            extra = ", ".join(sorted(kwargs.keys()))
            raise TypeError(f"Unexpected keyword arguments for Handler(...): {extra}")

        return HandlerFactory(
            msg_type=msg_type,
            name=name,
            kind=(kind or name),
            validators=validators,
            desc=desc,
        )

class Handler(Typed, metaclass=HANDLER):
    pass

class handler:
    propagate = _propagate
    @typed
    def data(
        handler: Handler,
        callback:  Maybe(Callable) = None,
        propagate: Status = "success",
        **kwargs:  Dict(Str),
    ) -> Maybe(Data):
        h = handler
        res = h(**kwargs)
        if propagate == "failure":
            _propagate.failure(res)
        if propagate == "success":
            _propagate.success(res)

        if callback:
            return callback(res.data)
        return res.data

    @typed
    def success(
        message: Maybe(Str) = None,
        data:    Maybe(Data) = None,
        code:    Maybe(Int) = None,
        **kwargs: Dict(Str)
    ) -> Message:
        return Message(
            message=_message(message=message, **kwargs),
            data=data,
            status="success",
            success=True,
            code=code
        )

    @typed
    def failure(
        message: Maybe(Str) = None,
        data:    Maybe(Data) = None,
        code:    Maybe(Int) = None,
        **kwargs: Dict(Str)
    ) -> Message:
        return Message(
            message=_message(message=message, **kwargs),
            data=data,
            status="failure",
            success=False,
            code=code
        )

    def __new__(cls, f=None, **kwargs):
        Error = kwargs.pop("enclose", None)
        error_message = kwargs.pop("message", None)

        def _decorate(func):
            @wraps(func)
            def core(*args, **kw):
                try:
                    try:
                        return func(*args, **kw)
                    except Propagate as exc:
                        return exc.msg
                except BaseException as e:
                    if Error is not None and not isinstance(e, Propagate):
                        msg = error_message if error_message is not None else str(e)
                        raise Error(msg) from e
                    raise

            core.__annotations__ = getattr(func, "__annotations__", {}).copy()

            typed_f = typed(core, **kwargs)

            if not hasattr(typed_f, "cod") or not (typed_f.cod <= Message):
                raise TypeError(
                     "Codomain mismatch in handler:\n"
                    f"  ==> '{func.__name__}': A handler should return an instance of 'Message'.\n"
                     "      [expected_type] subtype of 'Message'\n"
                    f"      [received_type] '{name(typed_f.cod)}'"
                )

            typed_f.is_propagator = True
            typed_f.is_handler = True
            return typed_f

        if f is not None and callable(f):
            return _decorate(f)

        _decorate.data = cls.data
        _decorate.success = cls.success
        _decorate.failure = cls.failure
        _decorate.propagate = cls.propagate
        return _decorate

@model
class HandlerInfo:
    path: Tuple(Str)
    name: Str
    func: Handler
    owner: Any
    meta: Dict


def register_handler(system, path, name, func, owner, meta=None):
    info = HandlerInfo(
        path=path,
        name=name,
        func=func,
        owner=owner,
        meta=dict(meta or {}),
    )
    system._handlers[path] = info

    if path and len(path) == 1:
        head = path[0]

        if hasattr(system, "get"):
            setattr(system.get, head, func)

        if hasattr(system, "info"):
            setattr(system.info, head, _InfoProxy(system, (head,)))

    return info

def handler_method(self, path: str, name=None, **meta):
    rel_path = _normalize_path(path)

    def decorator(func):
        h = handler(func)
        h_name = name or getattr(func, "__name__", "handler")

        if hasattr(self, "_local_handlers"):
            entry = HandlerInfo(
                path=rel_path,
                name=h_name,
                func=h,
                owner=self,
                meta=dict(meta),
            )
            self._local_handlers[rel_path] = entry

            if not hasattr(self, h_name):
                setattr(self, h_name, h)

            system = getattr(self, "system", None)
            if system is not None:
                abs_path = self.prefix + rel_path
                register_handler(
                    system,
                    path=abs_path,
                    name=entry.name,
                    func=h,
                    owner=self,
                    meta=entry.meta,
                )

        else:
            abs_path = rel_path
            register_handler(
                self,
                path=abs_path,
                name=h_name,
                func=h,
                owner=self,
                meta=meta,
            )
            if abs_path:
                last_seg = abs_path[-1]
                if last_seg and not hasattr(self, last_seg):
                    setattr(self, last_seg, h)
        return h
    return decorator
