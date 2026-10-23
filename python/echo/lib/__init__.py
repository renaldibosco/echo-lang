"""Built-in function registry. Each library module registers functions with @builtin."""
from ..values import Builtin

REGISTRY = {}
CATEGORIES = {}


def builtin(name, category, doc="", needs_interp=False, aliases=()):
    def wrap(fn):
        b = Builtin(name, fn, needs_interp=needs_interp, doc=doc)
        REGISTRY[name] = b
        CATEGORIES.setdefault(category, []).append((name, doc))
        return fn  # Echo 2 has one name per function, so `aliases` are ignored
    return wrap


def constant(name, category, value, doc=""):
    REGISTRY[name] = value
    CATEGORIES.setdefault(category, []).append((name, doc))
