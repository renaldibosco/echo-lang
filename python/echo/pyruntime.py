"""Runtime for Python code made by `echolang python`. Converted programs start with
    from echo.pyruntime import *
so every Echo built-in and module (length, bio.gc, math.round, stats.mean, ai.ask, ...) works the same."""
import builtins as _bi
import types as _types

from .errors import EchoError, EchoRuntimeError, EchoTypeError
from .interpreter import Interpreter, error_record as _error_record
from .parser import Parser
from .lexer import tokenize
from .values import Builtin, describe_value, matches, show, truthy

_interp = Interpreter()
__all__ = ["and_", "or_", "not_", "say", "add", "div", "xor", "nand", "nor", "xnor", "erange", "each", "pairs",
           "attr", "record", "ask", "add_to", "EchoError", "show", "cond", "error_record", "times", "typed",
           "set_field"]


def _wrap(b):
    if isinstance(b, Builtin):
        def call(*a, **k):
            return _interp.call_value(b, list(a), k)
        call.__name__ = b.name
        return call
    return b


_EXPORTS = {n: _wrap(v) for n, v in _interp.builtins.items()}
for _name, _mod in _interp.modules.items():
    _EXPORTS[_name] = _types.SimpleNamespace(**{k: _wrap(v) for k, v in _mod.members.items()})
__all__ += [n for n in _EXPORTS if n not in __all__]


def __getattr__(name):  # Echo built-ins, without hiding Python's own names inside this file
    try:
        return _EXPORTS[name]
    except KeyError:
        raise AttributeError(name)


_SPECS = {}
_RECORDS = {}


def _spec(text):
    if text not in _SPECS:
        _SPECS[text] = Parser(tokenize(text)).type_spec()
    return _SPECS[text]


def typed(value, spec, what):
    """Raise E302 unless value fits the Echo type written as text, e.g. "list of dna"."""
    s = _spec(spec)
    if not matches(value, s) and not (_bi.isinstance(value, _bi.dict) and value.get("_type") == s.name):
        raise EchoTypeError("%s must be %s, but got %s." % (what, spec, describe_value(value)), code="E302")
    return value


def say(*values):
    _bi.print(" ".join(show(v) for v in values))


def add(a, b):
    return _interp.binop("+", a, b, None)


def div(a, b):
    return _interp.binop("/", a, b, None)


def cond(v, word="if"):
    if not _bi.isinstance(v, _bi.bool):
        raise EchoTypeError("The %s condition must be true or false, not %s." % (word, describe_value(v)), code="E303")
    return v


def _bit(v):
    return _bi.isinstance(v, _bi.int) and not _bi.isinstance(v, _bi.bool) and v in (0, 1)


def _gate(op, a, b):
    if not ((_bi.isinstance(a, _bi.bool) and _bi.isinstance(b, _bi.bool)) or (_bit(a) and _bit(b))):
        raise EchoTypeError("'%s' needs both sides to be true/false, or both to be bits (0 or 1); got %s and %s."
                            % (op, describe_value(a), describe_value(b)))
    x, y = _bi.bool(a), _bi.bool(b)
    r = {"and": x and y, "or": x or y, "xor": x != y, "nand": not (x and y),
         "nor": not (x or y), "xnor": x == y}[op]
    return r if _bi.isinstance(a, _bi.bool) else (1 if r else 0)


def and_(a, b):
    """Echo `a and b`; b is a function so it only runs when needed."""
    if (_bi.isinstance(a, _bi.bool) or _bit(a)) and not a:
        return a
    return _gate("and", a, b())


def or_(a, b):
    if _bi.isinstance(a, _bi.bool) and a:
        return True
    if _bit(a) and a == 1:
        return 1
    return _gate("or", a, b())


def not_(a):
    if _bi.isinstance(a, _bi.bool):
        return not a
    if _bit(a):
        return 1 - a
    raise EchoTypeError("'not' needs true/false or a bit (0 or 1), not %s." % describe_value(a))


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
    if _bi.isinstance(it, _bi.dict):
        return [k for k in it if k != "_type"]
    if not _bi.isinstance(it, (_bi.list, _bi.str, _bi.tuple)):
        raise EchoTypeError("Can't loop over %s." % describe_value(it))
    return it


def pairs(it):
    if _bi.isinstance(it, _bi.dict):
        return [(k, v) for k, v in it.items() if k != "_type"]
    return _bi.list(_bi.enumerate(it))


def attr(obj, name):
    if _bi.isinstance(obj, _bi.dict) and name in obj and name != "_type":
        return obj[name]
    raise EchoRuntimeError("No field '%s'." % name, code="E202")


def set_field(obj, name, value):
    if not _bi.isinstance(obj, _bi.dict):
        raise EchoTypeError("Only maps and records have fields you can set.")
    rec = _RECORDS.get(obj.get("_type"))
    if rec is not None:
        if name not in rec:
            raise EchoRuntimeError("Record %s has no field '%s'." % (obj["_type"], name), code="E202")
        if rec[name]:
            typed(value, rec[name], "Field %s.%s" % (obj["_type"], name))
    obj[name] = value


_MISSING = object()


def record(name, fields, defaults=None, field_types=None):
    defaults = defaults or {}
    field_types = field_types or {}
    _RECORDS[name] = {f: field_types.get(f) for f in fields}

    def make(*args, **kwargs):
        if _bi.len(args) > _bi.len(fields):
            raise EchoRuntimeError("%s() takes %d values but got %d." % (name, _bi.len(fields), _bi.len(args)),
                                   code="E203")
        obj = {"_type": name}
        for i, f in _bi.enumerate(fields):
            if i < _bi.len(args):
                v = args[i]
            elif f in kwargs:
                v = kwargs.pop(f)
            elif f in defaults:
                v = defaults[f]()
            else:
                raise EchoRuntimeError("%s() is missing the value for '%s'." % (name, f), code="E205")
            if field_types.get(f):
                typed(v, field_types[f], "Field %s.%s" % (name, f))
            obj[f] = v
        if kwargs:
            raise EchoRuntimeError("%s has no field '%s'." % (name, _bi.next(_bi.iter(kwargs))), code="E204")
        return obj
    make.__name__ = name
    return make


def ask(prompt):
    answer = _bi.input(show(prompt) + " ")
    t = answer.strip()
    if t and t[0] in "+-0123456789.":
        try:
            return _bi.float(t) if _bi.any(c in t for c in ".eE") else _bi.int(t)
        except ValueError:
            pass
    return answer


def times(n):
    """Echo `repeat n times`."""
    return _bi.range(_bi.int(n))


def add_to(target, value):
    if not _bi.isinstance(target, _bi.list):
        raise EchoTypeError("'add ... to' needs a list, not %s." % describe_value(target))
    target.append(value)
    return target


def error_record(e):
    if _bi.isinstance(e, EchoError):
        return _error_record(e)
    if _bi.isinstance(e, ZeroDivisionError):
        return {"_type": "Error", "code": "E401", "message": "Division by zero.", "line": None}
    if _bi.isinstance(e, RecursionError):
        return {"_type": "Error", "code": "E405", "message": "Too much recursion.", "line": None}
    return {"_type": "Error", "code": "E404", "message": _bi.str(e), "line": None}


truthy = truthy
