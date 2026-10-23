"""Echo runtime values and how they print."""
import math


class EchoFunction:
    def __init__(self, name, params, body, closure, is_lambda=False, returns=None):
        self.name = name
        self.params = params      # list of (name, default_node or None, TypeSpec or None)
        self.body = body          # list of statements, or an expression node for lambdas
        self.closure = closure
        self.is_lambda = is_lambda
        self.returns = returns    # TypeSpec or None

    def __repr__(self):
        return "<function %s>" % self.name


class Builtin:
    def __init__(self, name, fn, needs_interp=False, doc="", qualname=None):
        self.name = name              # internal name (also the Java runtime name)
        self.fn = fn
        self.needs_interp = needs_interp
        self.doc = doc
        self.qualname = qualname or name   # how Echo code writes it, e.g. bio.gc

    def __repr__(self):
        return "<built-in %s>" % self.qualname


class Module:
    """A built-in module (bio, math, ...) or a .echo file loaded with `use`."""

    def __init__(self, name, members, doc=""):
        self.name = name
        self.members = members    # name -> value
        self.doc = doc

    def __repr__(self):
        return "<module %s>" % self.name


class RecordType:
    """What `record Gene(name: text, seq: dna = "")` creates: a constructor that knows its field types."""

    def __init__(self, name, fields, make):
        self.name = name
        self.fields = fields      # list of (name, default_node, TypeSpec or None)
        self.make = make

    def __repr__(self):
        return "<record %s>" % self.name


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
    return "%.10g" % v


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
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        t = v.get("_type", "map")
        return t if isinstance(t, str) else "map"
    if isinstance(v, Module):
        return "module"
    if isinstance(v, (EchoFunction, Builtin, RecordType)) or callable(v):
        return "function"
    return type(v).__name__


def truthy(v):
    """Used by built-ins such as filter(); conditions in if/while must be real booleans."""
    if v is None:
        return False
    if isinstance(v, (bool, int, float)):
        return v != 0
    if isinstance(v, (str, list, tuple, dict)):
        return len(v) > 0
    return True


# ------------------------------------------------------------------ types
BASE_TYPES = {"any", "number", "integer", "text", "boolean", "list", "map", "function", "nothing",
              "dna", "rna", "protein"}
_DNA = set("ACGTNacgtn")
_RNA = set("ACGUNacgun")
_PROTEIN = set("ACDEFGHIKLMNPQRSTVWYXBZUO*acdefghiklmnpqrstvwyxbzuo")


def matches(value, spec, records=()):
    """True if value fits the TypeSpec. `records` holds the names of record types in the program."""
    if spec is None:
        return True
    if value is None and (spec.optional or spec.name in ("nothing", "any")):
        return True
    name = spec.name
    if name == "any":
        return True
    if name == "nothing":
        return value is None
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or \
               (isinstance(value, float) and value == int(value))
    if name == "boolean":
        return isinstance(value, bool)
    if name in ("text", "dna", "rna", "protein"):
        if not isinstance(value, str):
            return False
        allowed = {"text": None, "dna": _DNA, "rna": _RNA, "protein": _PROTEIN}[name]
        return allowed is None or all(c in allowed for c in value)
    if name == "list":
        return isinstance(value, list) and (spec.of is None or all(matches(x, spec.of, records) for x in value))
    if name == "map":
        return isinstance(value, dict) and "_type" not in value and \
            (spec.of is None or all(matches(x, spec.of, records) for x in value.values()))
    if name == "function":
        return isinstance(value, (EchoFunction, Builtin, RecordType)) or callable(value)
    # a record name
    return isinstance(value, dict) and value.get("_type") == name


def describe_value(v):
    """Short description of a value for type errors: 'text "ATGX"', 'number 5'."""
    t = type_name(v)
    if isinstance(v, (str, int, float)) and not isinstance(v, bool):
        s = show(v, True)
        if len(s) > 24:
            s = s[:21] + '..."'
        return "%s %s" % (t, s)
    return t
