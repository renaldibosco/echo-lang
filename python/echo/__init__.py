"""Echo: an English-like programming language for biology, logic, cyber and AI."""
__version__ = "2.0.0"

from .errors import EchoError  # noqa: E402
from .interpreter import Interpreter, run_source  # noqa: E402
from .parser import parse  # noqa: E402
from .checker import check_source  # noqa: E402
from .formatter import format_source  # noqa: E402


def run(source, **kw):
    """Run Echo code and return the collected output as text."""
    lines = []
    ok, err = run_source(source, output=lines.append, **kw)
    if not ok:
        lines.append(err)
    return "\n".join(lines)
