"""Bridge between the Android app (Java) and the Echo interpreter (Python)."""
import os
import traceback

import echo
from echo.interpreter import run_source

EXAMPLES_DIR = os.path.join(os.path.dirname(echo.__file__), "examples")
ORDER = ["hello", "bio", "games", "gates", "cyber", "ml", "ai"]


def run(code, bridge, files_dir, provider, key, model):
    os.environ["ECHO_HOME"] = files_dir
    for name, value in (("ECHO_AI_PROVIDER", provider), ("ECHO_AI_KEY", key), ("ECHO_AI_MODEL", model)):
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    try:
        os.chdir(files_dir)
        ok, err = run_source(code, output=lambda s: bridge.say(s), input_fn=lambda p: bridge.ask(p),
                             should_stop=lambda: bridge.stopRequested(),
                             filename=os.path.join(files_dir, "main.echo"))
        if not ok:
            bridge.error(err)
    except Exception:
        bridge.error("Internal error:\n" + traceback.format_exc(limit=3))
    finally:
        bridge.done()


def to_java(code, class_name):
    from echo.transpile.java import to_java as conv
    try:
        return conv(code, class_name or "Program")
    except echo.EchoError as e:
        return "// Could not convert:\n// " + str(e).replace("\n", "\n// ")


def to_python(code):
    from echo.transpile.python import to_python as conv
    try:
        return conv(code)
    except echo.EchoError as e:
        return "# Could not convert:\n# " + str(e).replace("\n", "\n# ")


def java_runtime():
    path = os.path.join(os.path.dirname(echo.__file__), "java", "echo", "EchoRuntime.java")
    with open(path, encoding="utf-8") as f:
        return f.read()


def examples():
    names = [f[:-5] for f in os.listdir(EXAMPLES_DIR) if f.endswith(".echo")]
    return sorted(names, key=lambda n: (ORDER.index(n) if n in ORDER else 99, n))


def example(name):
    with open(os.path.join(EXAMPLES_DIR, name + ".echo"), encoding="utf-8") as f:
        return f.read()


def check(code):
    """Returns '' if the code parses, else the error message."""
    try:
        echo.parse(code)
        return ""
    except echo.EchoError as e:
        return str(e)


def reference():
    from echo.stdlib import categories
    lines = [SYNTAX.strip(), ""]
    for cat, items in categories().items():
        lines.append("== %s ==" % cat.upper())
        for name, doc in items:
            lines.append("  " + (doc or name))
        lines.append("")
    return "\n".join(lines)


SYNTAX = """
ECHO QUICK GUIDE
One statement per line. Blocks end with `end`. Comments start with #.

set x to 5          x = 5          x += 1
say "GC is {gc(seq)}%"             (put code inside {} in text)
ask "Your name?" into name
ask ai "Explain PCR" into answer   (needs your AI key)

if x > 3 then ... else if x > 1 then ... else ... end
repeat 3 times ... end             repeat forever ... end
while x < 10 ... end
for each item in list ... end      for each key, value in map ... end
for i from 1 to 10 step 2 ... end
break  /  continue                 (also: stop / skip)

define area(w, h = 1) ... return w * h end
set double to fn(x) -> x * 2
try ... catch problem ... end      fail "message"
record Gene(name, seq = "")        Gene("gfp", "ATG")
use "other.echo"

Values: 12  3.5  "text"  true/false (yes/no)  nothing
Lists: [1, 2, 3]  (positions start at 0)  items[0]  items[1:3]
Maps:  {name: "gfp", length: 720}   m.name   m["name"]
Maths: + - * / // % ^      Compare: == != < > <= >= is, is not, in, not in
Logic gates: and or not xor nand nor xnor   (1/0 give 1/0, true/false give true/false)
Call styles: gc(seq)   gc of seq   seq.gc()
"""
