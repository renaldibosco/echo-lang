"""Command line: echolang run file.echo | echolang (REPL) | echolang java file.echo | ..."""
import os
import sys

from . import __version__
from .errors import EchoError, EchoSyntaxError
from .interpreter import Interpreter, run_source, BreakSignal, ContinueSignal, ReturnSignal
from .parser import parse

USAGE = """Echo %s - English-like programming for biology

  echolang FILE.echo              run a program
  echolang run FILE.echo          run a program
  echolang                        interactive mode (type 'exit' to leave)
  echolang check FILE.echo        check the code without running it
  echolang java FILE.echo [-o X]  convert to Java
  echolang java --runtime DIR     write echo/EchoRuntime.java (needed by converted Java)
  echolang python FILE.echo [-o X] convert to Python
  echolang examples [NAME]        list or show the built-in examples
  echolang help [FUNCTION]        list functions or explain one
  echolang version
""" % __version__


def examples_dir():
    return os.path.join(os.path.dirname(__file__), "examples")


def read(path):
    if not os.path.exists(path) and os.path.exists(path + ".echo"):
        path += ".echo"
    with open(path, encoding="utf-8") as f:
        return f.read(), path


def repl():
    print("Echo %s. Type code, 'help()' for functions, 'exit' to leave." % __version__)
    interp = Interpreter()
    buf = []
    while True:
        try:
            line = input("... " if buf else "echo> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not buf and line.strip() in ("exit", "quit"):
            return
        buf.append(line)
        source = "\n".join(buf)
        try:
            tree = parse(source)
        except EchoSyntaxError as e:
            if "has no 'end'" in e.message or "no closing" in e.message:
                continue
            print(e)
            buf = []
            continue
        buf = []
        # show the value of a single expression, like Python
        if len(tree.body) == 1 and tree.body[0].kind == "ExprStmt":
            try:
                v = interp.eval(tree.body[0].expr, interp.globals)
                if v is not None:
                    interp.say(v)
            except EchoError as e:
                print(e)
            continue
        try:
            interp.exec_block(tree.body, interp.globals)
        except EchoError as e:
            print(e)
        except (BreakSignal, ContinueSignal, ReturnSignal):
            print("break, continue and return only work inside loops or functions.")


def convert(kind, args):
    if not args:
        print("Give a .echo file to convert.")
        return 1
    if kind == "java" and args[0] == "--runtime":
        import shutil
        dest = os.path.join(args[1] if len(args) > 1 else ".", "echo")
        os.makedirs(dest, exist_ok=True)
        src = os.path.join(os.path.dirname(__file__), "java", "echo", "EchoRuntime.java")
        shutil.copy(src, os.path.join(dest, "EchoRuntime.java"))
        print("Wrote", os.path.join(dest, "EchoRuntime.java"))
        return 0
    source, path = read(args[0])
    out = None
    if "-o" in args:
        out = args[args.index("-o") + 1]
    if kind == "java":
        from .transpile.java import to_java
        name = os.path.splitext(os.path.basename(path))[0]
        code = to_java(source, class_name=name)
    else:
        from .transpile.python import to_python
        code = to_python(source)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(code)
        print("Wrote", out)
    else:
        print(code)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        repl()
        return 0
    cmd = argv[0]
    try:
        if cmd in ("-h", "--help"):
            print(USAGE)
            return 0
        if cmd in ("version", "--version", "-v"):
            print("Echo", __version__)
            return 0
        if cmd == "help":
            from .lib.core import _help
            Interpreter().call_value(Interpreter().builtins["help"], argv[1:2])
            return 0
        if cmd == "examples":
            d = examples_dir()
            if len(argv) == 1:
                for f in sorted(os.listdir(d)):
                    if f.endswith(".echo"):
                        print(f[:-5])
                return 0
            print(read(os.path.join(d, argv[1]))[0])
            return 0
        if cmd == "check":
            source, path = read(argv[1])
            parse(source)
            print("No problems found in", path)
            return 0
        if cmd in ("java", "python"):
            return convert(cmd, argv[1:])
        if cmd == "run":
            argv = argv[1:]
        source, path = read(argv[0])
    except EchoError as e:
        print(e)
        return 1
    except OSError as e:
        print("Can't open the file:", e)
        return 1
    ok, err = run_source(source, filename=path)
    if not ok:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
