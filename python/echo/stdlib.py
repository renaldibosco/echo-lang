"""Loads every built-in library and returns name -> value."""
_loaded = None


def load():
    global _loaded
    if _loaded is None:
        from .lib import REGISTRY
        from .lib import core, bio, gates, cyber, ml, ai  # noqa: F401  (registers functions)
        _loaded = REGISTRY
    return dict(_loaded)


def categories():
    load()
    from .lib import CATEGORIES
    return CATEGORIES
