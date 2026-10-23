"""Loads every built-in library."""
_loaded = None


def raw():
    """Internal name -> value, exactly as the library files registered them."""
    global _loaded
    if _loaded is None:
        from .lib import REGISTRY
        from .lib import core, bio, gates, cyber, ml, ai  # noqa: F401  (registers functions)
        _loaded = REGISTRY
    return _loaded


def load():
    """(globals, modules) as Echo code sees them."""
    from .modules import GLOBALS, MODULES, build
    build()
    return GLOBALS, MODULES


def categories():
    raw()
    from .lib import CATEGORIES
    return CATEGORIES
