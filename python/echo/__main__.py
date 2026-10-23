"""Command line for Echo."""
import os
import sys

from . import __version__
from .errors import EchoError, EchoSyntaxError
from .interpreter import Interpreter, run_source

USAGE = """Echo %s - an English-like programming language for biology

Usage:
  echolang FILE.echo                 run a program (same as: echolang run FILE.echo)
  echolang                           interactive mode (type 'exit' to leave)
  echolang check FILE.echo...        find mistakes without running (errors and warnings)
  echolang fmt FILE.echo...          rewrite files in the standard layout (--check: only report)
  echolang upgrade FILE.echo...      convert Echo 1 code to Echo 2 (-w: overwrite the files)
  echolang explain CODE              explain an error code, e.g. echolang explain E302
  echolang java FILE.echo [-o OUT]   convert to Java
  echolang java --runtime DIR        write echo/EchoRuntime.java (needed by converted Java)
  echolang python FILE.echo [-o OUT] convert to Python
  echolang examples [NAME]           list or show the built-in examples
  echolang help [NAME]               list everything, a module (bio) or one function (bio.gc)
  echolang version
""" % __version__


def examples_dir():
    return os.path.join(os.path.dirname(__file__), "examples")


def read(path):
    if not os.path.exists(path) and os.path.exists(path + ".echo"):
        path += ".echo"
    with open(path, encoding="utf-8") as f:
        return f.read(), path


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def repl():
    print("Echo %s. Type code, help() for functions, exit to leave." % __version__)
    from .parser import parse
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
            if e.code in ("E102", "E103"):
                continue
            print(e)
            buf = []
            continue
        buf = []
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


def cmd_check(paths):
    from .checker import check_source
    errors = warnings = 0
    for p in paths:
        source, path = read(p)
        diags = check_source(source)
        for d in diags:
            print(d.format(path))
        e = sum(d.is_error for d in diags)
        errors += e
        warnings += len(diags) - e
    if errors or warnings:
        print("%d error%s, %d warning%s." % (errors, "" if errors == 1 else "s", warnings,
                                             "" if warnings == 1 else "s"))
    else:
        print("No problems found.")
    return 1 if errors else 0


def cmd_fmt(args):
    from .formatter import format_source
    check_only = "--check" in args
    paths = [a for a in args if not a.startswith("--")]
    bad = 0
    for p in paths:
        source, path = read(p)
        new = format_source(source)
        if new != source:
            bad += 1
            if check_only:
                print("would reformat", path)
            else:
                write(path, new)
                print("formatted", path)
    if check_only:
        print("%d file%s need formatting." % (bad, "" if bad == 1 else "s") if bad else "All files are formatted.")
        return 1 if bad else 0
    if not bad:
        print("Nothing to change.")
    return 0


def cmd_upgrade(args):
    from .upgrade import upgrade_source
    from .checker import check_source
    in_place = "-w" in args
    paths = [a for a in args if not a.startswith("-")]
    for p in paths:
        source, path = read(p)
        new, notes = upgrade_source(source)
        if in_place:
            write(path, new)
            print("upgraded", path)
        else:
            print(new, end="")
        for n in notes:
            print("note:", n, file=sys.stderr)
        problems = [d for d in check_source(new) if d.is_error]
        for d in problems:
            print(d.format(path), file=sys.stderr)
        if problems:
            print("%d thing%s still need a person to fix (see above)." % (len(problems), "" if len(problems) == 1
                                                                          else "s"), file=sys.stderr)
    return 0


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
    out = args[args.index("-o") + 1] if "-o" in args else None
    if kind == "java":
        from .transpile.java import to_java
        code = to_java(source, class_name=os.path.splitext(os.path.basename(path))[0])
    else:
        from .transpile.python import to_python
        code = to_python(source)
    if out:
        write(out, code)
        print("Wrote", out)
    else:
        print(code)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        repl()
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd in ("-h", "--help"):
            print(USAGE)
            return 0
        if cmd in ("version", "--version", "-v"):
            print("Echo", __version__)
            return 0
        if cmd == "help":
            interp = Interpreter()
            interp.call_value(interp.builtins["help"], rest[:1])
            return 0
        if cmd == "explain":
            from .errors import explain
            print(explain(rest[0]) if rest else "Give a code, e.g. echolang explain E201")
            return 0
        if cmd == "examples":
            d = examples_dir()
            if not rest:
                for f in sorted(os.listdir(d)):
                    if f.endswith(".echo"):
                        print(f[:-5])
                return 0
            print(read(os.path.join(d, rest[0]))[0], end="")
            return 0
        if cmd == "check":
            return cmd_check(rest)
        if cmd == "fmt":
            return cmd_fmt(rest)
        if cmd == "upgrade":
            return cmd_upgrade(rest)
        if cmd in ("java", "python"):
            return convert(cmd, rest)
        if cmd == "run":
            argv = rest
        source, path = read(argv[0])
    except EchoError as e:
        print(e, file=sys.stderr)
        return 1
    except OSError as e:
        print("Can't open the file:", e, file=sys.stderr)
        return 1
    ok, err = run_source(source, filename=path)
    if not ok:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
