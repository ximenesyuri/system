import functools
from typed import typed, model, Str, Int, Bytes, Maybe, Dict, Union, Any, Bool, Enum
from typed.models import MODEL, LAZY_MODEL, validate
from utils import func
from utils.types import Json, Client
from utils.general import Message

Data = Union(Json, Str, Int, Bytes)
Status = Enum(Str, "success", "failure")
Model = Union(MODEL, LAZY_MODEL)

@model
class Result:
    message: Maybe(Str)=None
    data:    Maybe(Data)=None
    success: Bool=True
    code:    Maybe(Int)=None

Result.__display__ = "Result"

class _Propagate(Exception):
    def __init__(self, result):
        self.result = result

class propagate:
    @typed
    def failure(res: Result) -> Result:
        if not res.success:
            raise _Propagate(res)
        return res

    @typed
    def success(res: Result) -> Result:
        if res.success:
            raise _Propagate(res)
        return res

class result:
    @typed
    def success(
        action:   Any=None,
        message:  Maybe(Str)=None,
        data:     Maybe(Data)=None,
        code:     Maybe(Int)=None,
        **kwargs: Dict(Str)
    ) -> Result:
        if action is not None:
            if message is not None or data is not None:
                raise ValueError("Cannot simultaneously set an action and a message/data")
            return action(**kwargs).success
        return Result(
            message=Message(message=message, **kwargs) if message or kwargs else None,
            data=data,
            success=True,
            code=code
        )

    @typed
    def failure(
        action: Any=None,
        message: Maybe(Str)=None,
        data: Maybe(Data)=None,
        code: Maybe(Int)=None,
        **kwargs: Dict(Str)
    ) -> Result:
        if action is not None:
            if message is not None or data is not None:
                raise ValueError("Cannot simultaneously set an action and a message/data")
            return not action(**kwargs).success
        return Result(
            message=Message(message=message, **kwargs) if message or kwargs else None,
            data=data,
            code=code,
            success=False
        )

    @typed
    def data(
        action:    Any,
        model:     Maybe(Model)=None,
        propagate: Status="failure",
        **kwargs: Dict(Str)
    ) -> Data:
        res = action(**kwargs)
        if propagate == "failure":
            globals()['propagate'].failure(res)
        if propagate == "success":
            globals()['propagate'].success(res)
        if model:
            return validate(res.data, model)
        return res.data

class Action:
    success = staticmethod(result.success)
    failure = staticmethod(result.failure)
    data = staticmethod(result.data)
    propagate = propagate

    @typed
    def run(
        action:    Any,
        model:     Maybe(Model)=None,
        propagate: Status="failure",
        **kwargs:  Dict(Str)
    ) -> Result:
        res = action(**kwargs)
        if propagate == "failure":
            globals()['propagate'].failure(res)
        if propagate == "success":
            globals()['propagate'].success(res)
        if model:
            validate(res.data, model)
        return res

    def __init__(self, Error=None, message=None):
        if Error is None:
            typed_ = typed
        elif isinstance(Error, type) and issubclass(Error, BaseException):
            if message:
                typed_ = func.eval(typed, enclose=Error, message=message)
            else:
                typed_ = func.eval(typed, enclose=Error)
        elif Error in Str:
            exc_type = type(Error, (Exception,), {})
            if message:
                typed_ = func.eval(typed, enclose=exc_type, message=message)
            else:
                typed_ = func.eval(typed, enclose=exc_type)
        else:
            raise TypeError("Error must be an exception class or a string")

        self._typed = typed_

    def __call__(self, func=None, **kwargs):
        typed_ = self._typed

        def apply(f):
            typed_func = typed_(f, **kwargs)
            cod = getattr(typed_func, "cod", None)
            if cod is not Result and not (isinstance(cod, type) and issubclass(cod, Client)):
                from typed import name
                raise TypeError(
                    f"Codomain mismatch in function '{name(f)}':\n"
                    "    [expected_type] 'Result'\n"
                    f"    [received_type] '{name(cod)}'"
                )

            if cod is Result:
                @functools.wraps(f)
                def wrapper(*args, **kw):
                    try:
                        return typed_func(*args, **kw)
                    except _Propagate as exc:
                        return exc.result

                wrapper.cod = cod
                if hasattr(typed_func, "dom"):
                    wrapper.dom = typed_func.dom
                return wrapper

            return typed_func

        if func is None:
            return apply
        else:
            return apply(func)
