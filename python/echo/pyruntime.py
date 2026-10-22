"""Runtime for Python code made by `echolang python`. Converted programs start with
    from echo.pyruntime import *
so every Echo built-in (gc, translate, design_primers, sha256, train, ai, ...) works the same."""
import builtins as _bi

from .errors import EchoError, EchoRuntimeError
from .interpreter import Interpreter
from .values import BoundBuiltin, Builtin, show, truthy

_interp = Interpreter()
__all__ = ["and_", "or_", "not_", "say", "add", "div", "xor", "nand", "nor", "xnor", "erange", "each", "pairs", "attr", "record",
           "ask", "add_to", "EchoError", "show", "truthy", "message", "times"]


def _wrap(b):
    if isinstance(b, Builtin):
        if b.needs_interp:
            return lambda *a, **k: b.fn(_interp, *a, **k)
        return b.fn
    return b


_EXPORTS = {n: _wrap(v) for n, v in _interp.builtins.items()}
__all__ += [n for n in _EXPORTS if n not in __all__]


def __getattr__(name):  # Echo built-ins, without hiding Python's own names inside this file
    try:
        return _EXPORTS[name]
    except KeyError:
        raise AttributeError(name)


def say(*values):
    _bi.print(" ".join(show(v) for v in values))


def add(a, b):
    return _interp.binop("+", a, b, None)


def div(a, b):
    return _interp.binop("/", a, b, None)


def _bit(v):
    return isinstance(v, int) and not isinstance(v, bool) and v in (0, 1)


def _gate(op, a, b):
    x, y = truthy(a), truthy(b)
    r = {"and": x and y, "or": x or y, "xor": x != y, "nand": not (x and y),
         "nor": not (x or y), "xnor": x == y}[op]
    return (1 if r else 0) if _bit(a) and _bit(b) else r


def and_(a, b):
    """Echo `a and b`; b is a function so it only runs when needed."""
    if not truthy(a):
        return 0 if _bit(a) else False
    return _gate("and", a, b())


def or_(a, b):
    if truthy(a):
        return 1 if _bit(a) else True
    return _gate("or", a, b())


def not_(a):
    return 1 - a if _bit(a) else not truthy(a)


def xor(a, b):
    return _gate("xor", a, b)


def nand(a, b):
    return _gate("nand", a, b)


def nor(a, b):
    return _gate("nor", a, b)


def xnor(a, b):
    return _gate("xnor", a, b)


def erange(a, b, step=None):
    """Echo `for i from a to b step s` (b included)."""
    if step is None:
        step = 1 if b >= a else -1
    i = a
    while (i <= b) if step > 0 else (i >= b):
        yield i
        i += step


def each(it):
    if isinstance(it, dict):
        return [k for k in it if k != "_type"]
    if isinstance(it, (int, float)):
        return _bi.range(_bi.int(it))
    return it


def pairs(it):
    if isinstance(it, dict):
        return [(k, v) for k, v in it.items() if k != "_type"]
    return _bi.list(_bi.enumerate(it))


def attr(obj, name):
    if isinstance(obj, dict) and name in obj:
        return obj[name]
    b = _interp.builtins.get(name)
    if isinstance(b, Builtin):
        f = _wrap(b)
        return lambda *a, **k: f(obj, *a, **k)
    raise EchoRuntimeError("No field '%s'." % name)


def record(name, fields, defaults=None):
    defaults = defaults or {}

    def make(*args, **kwargs):
        obj = {"_type": name}
        for i, f in enumerate(fields):
            obj[f] = args[i] if i < len(args) else kwargs.get(f, defaults.get(f))
        return obj
    return make


def ask(prompt):
    answer = _bi.input(show(prompt) + " ")
    try:
        return _bi.int(answer)
    except ValueError:
        try:
            return _bi.float(answer)
        except ValueError:
            return answer


def times(n):
    """Echo `repeat n times`."""
    return _bi.range(_bi.int(n))


def add_to(target, value):
    if isinstance(target, list):
        target.append(value)
        return target
    return add(target, value)


def message(e):
    if isinstance(e, EchoError):
        return e.message
    if isinstance(e, ZeroDivisionError):
        return "Can't divide by zero."
    return _bi.str(e)
