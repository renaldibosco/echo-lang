"""Echo runtime values and how they print."""
import math


class EchoFunction:
    def __init__(self, name, params, body, closure, is_lambda=False):
        self.name = name
        self.params = params      # list of (name, default_node or None)
        self.body = body          # list of statements, or an expression node for lambdas
        self.closure = closure
        self.is_lambda = is_lambda

    def __repr__(self):
        return "<function %s>" % self.name


class Builtin:
    def __init__(self, name, fn, needs_interp=False, doc=""):
        self.name = name
        self.fn = fn
        self.needs_interp = needs_interp
        self.doc = doc

    def __repr__(self):
        return "<built-in %s>" % self.name


class BoundBuiltin:
    """`seq.gc()` style: calls a built-in with the value as its first argument."""

    def __init__(self, builtin, first):
        self.builtin = builtin
        self.first = first

    def __repr__(self):
        return "<built-in %s>" % self.builtin.name


def format_number(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if math.isnan(v):
        return "not a number"
    if math.isinf(v):
        return "infinity" if v > 0 else "-infinity"
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    text = "%.10g" % v
    return text


def show(v, nested=False):
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return format_number(v)
    if isinstance(v, str):
        if nested:
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
        return v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(show(x, True) for x in v) + "]"
    if isinstance(v, dict):
        if "_type" in v:
            inner = ", ".join("%s: %s" % (k, show(x, True)) for k, x in v.items() if k != "_type")
            return "%s(%s)" % (v["_type"], inner)
        return "{" + ", ".join("%s: %s" % (show(k, True) if not isinstance(k, str) else k, show(x, True))
                               for k, x in v.items()) + "}"
    return repr(v)


def type_name(v):
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "yes/no"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return v.get("_type", "map") if isinstance(v.get("_type", "map"), str) else "map"
    if isinstance(v, (EchoFunction, Builtin, BoundBuiltin)):
        return "function"
    return type(v).__name__


def truthy(v):
    if v is None:
        return False
    if isinstance(v, (bool, int, float)):
        return v != 0
    if isinstance(v, (str, list, tuple, dict)):
        return len(v) > 0
    return True
