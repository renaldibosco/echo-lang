"""Bridge between the Android app (Java) and the Echo interpreter (Python)."""
import os
import traceback

import echo
from echo.interpreter import run_source

EXAMPLES_DIR = os.path.join(os.path.dirname(echo.__file__), "examples")
ORDER = ["hello", "bio", "types", "control", "gates", "cyber", "ml", "ai"]


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
    """'' if there are no problems, else one line per error or warning."""
    from echo.checker import check_source
    return "\n".join(d.format() for d in check_source(code))


def needs_upgrade(code):
    from echo.checker import check_source
    return any(d.code == "E104" for d in check_source(code))


def upgrade(code):
    from echo.upgrade import upgrade_source
    try:
        return upgrade_source(code)[0]
    except echo.EchoError:
        return code


def format(code):  # noqa: A001  (called from Java)
    from echo.formatter import format_source
    try:
        return format_source(code)
    except echo.EchoError as e:
        return str(e)


def reference():
    from echo.modules import GLOBALS, MODULES, build
    from echo.values import Builtin
    build()
    lines = [SYNTAX.strip(), "", "== GLOBAL FUNCTIONS =="]
    for name in sorted(GLOBALS):
        v = GLOBALS[name]
        lines.append("  " + (v.doc if isinstance(v, Builtin) and v.doc else name))
    lines.append("")
    for mname in sorted(MODULES):
        mod = MODULES[mname]
        lines.append("== %s: %s ==" % (mname.upper(), mod.doc))
        for name in sorted(mod.members):
            v = mod.members[name]
            lines.append("  " + (v.doc if isinstance(v, Builtin) and v.doc else "%s.%s" % (mname, name)))
        lines.append("")
    return "\n".join(lines)


SYNTAX = """
ECHO 2 QUICK GUIDE
One statement per line. Blocks end with `end`. Comments start with #. Text uses "double quotes".

set x to 5                         set x to x + 1
set gc_target: number to 50        (types are optional: number integer text boolean list map dna rna protein)
say "GC is {bio.gc(seq)}%"         (put code inside {} in text)
ask "Your name?" into name

if x > 3 then ... else if x > 1 then ... else ... end    (conditions must be true or false)
repeat 3 times ... end             while x < 10 ... end
for each item in items ... end     for each key, value in map ... end
for i from 1 to 10 step 2 ... end  break   continue

define area(w: number, h: number = 1) -> number ... return w * h end
set double to fn(x) -> x * 2
try ... catch problem ... say problem.code, problem.message ... end     fail "message"
record Gene(name: text, seq: dna = "")        Gene("gfp", "ATG")
use "helpers.echo"                 then call helpers.function(...)

Values: 12  3.5  "text"  true  false  nothing
Lists: [1, 2, 3]  (positions start at 0)  items[0]  items[1:3]   add item to items
Maps:  {name: "gfp", length: 720}   m.name   m["name"]
Maths: + - * / // % ^      Compare: == != < > <= >= in, not in
Logic gates: and or not xor nand nor xnor   (true/false give true/false, 1/0 give 1/0)
Modules: bio math random file json time gates cyber stats ml ai  ->  bio.gc(seq), math.sqrt(2), ai.ask("...")
Errors have codes like E201. Check finds mistakes before you run. Format tidies the layout.
"""
