"""Echo -> Python converter. Output runs with `pip install` of this package (it imports echo.pyruntime)."""
import keyword

from ..modules import MODULES, build
from ..parser import parse
from .java import declared_types

BOOLISH = {"Compare", "Bool"}
PY_RESERVED = set(keyword.kwlist) | {"print_", "self"}


def name(n):
    return n + "_" if n in PY_RESERVED else n


class PyGen:
    def __init__(self, user_names=()):
        self.lines = []
        self.level = 0
        self.tmp = 0
        self.user_names = set(user_names)
        self.types = [{}]        # declared variable types per function level
        self.returns = [None]    # (TypeSpec, function name) per function level

    def emit(self, text):
        self.lines.append("    " * self.level + text)

    def block(self, body):
        self.level += 1
        if not body:
            self.emit("pass")
        for st in body:
            self.stmt(st)
        self.level -= 1

    # ---- statements ----
    def stmt(self, st):
        getattr(self, "st_" + st.kind)(st)

    def st_ExprStmt(self, st):
        self.emit(self.expr(st.expr))

    def st_Pass(self, st):
        self.emit("pass")

    def st_Say(self, st):
        self.emit("say(%s)" % ", ".join(self.expr(v) for v in st.values))

    def st_Set(self, st):
        value = self.expr(st.value)
        if st.target.kind == "Attr":
            self.emit("set_field(%s, %r, %s)" % (self.expr(st.target.obj), st.target.name, value))
            return
        if st.target.kind == "Name":
            spec = st.type or self.types[-1].get(st.target.name)
            if spec is not None:
                value = "typed(%s, %r, %r)" % (value, str(spec), "Variable '%s'" % st.target.name)
        self.emit("%s = %s" % (self.expr(st.target, store=True), value))

    def st_Add(self, st):
        self.emit("add_to(%s, %s)" % (self.expr(st.target), self.expr(st.value)))

    def st_Ask(self, st):
        self.emit("%s = ask(%s)" % (name(st.name), self.expr(st.prompt)))

    def cond(self, e, word):
        if e.kind in BOOLISH:
            return self.expr(e)
        return "cond(%s, %r)" % (self.expr(e), word)

    def st_If(self, st):
        for i, (cond, body) in enumerate(st.branches):
            self.emit("%s %s:" % ("if" if i == 0 else "elif", self.cond(cond, "if" if i == 0 else "else if")))
            self.block(body)
        if st.else_body is not None:
            self.emit("else:")
            self.block(st.else_body)

    def st_Repeat(self, st):
        self.emit("for _ in times(%s):" % self.expr(st.count))
        self.block(st.body)

    def st_While(self, st):
        self.emit("while %s:" % self.cond(st.cond, "while"))
        self.block(st.body)

    def st_ForEach(self, st):
        if st.var2:
            self.emit("for %s, %s in pairs(%s):" % (name(st.var), name(st.var2), self.expr(st.iterable)))
        else:
            self.emit("for %s in each(%s):" % (name(st.var), self.expr(st.iterable)))
        self.block(st.body)

    def st_ForRange(self, st):
        args = [self.expr(st.start), self.expr(st.stop)]
        if st.step is not None:
            args.append(self.expr(st.step))
        self.emit("for %s in erange(%s):" % (name(st.var), ", ".join(args)))
        self.block(st.body)

    def st_Break(self, st):
        self.emit("break")

    def st_Continue(self, st):
        self.emit("continue")

    def params(self, params):
        out = []
        for pname, default, _ in params:
            out.append(name(pname) if default is None else "%s=%s" % (name(pname), self.expr(default)))
        return ", ".join(out)

    def st_Define(self, st):
        self.emit("")
        self.emit("def %s(%s):" % (name(st.name), self.params(st.params)))
        types = declared_types(st.body)
        types.update({p: t for p, _, t in st.params if t is not None})
        self.types.append(types)
        self.returns.append((st.returns, st.name))
        self.level += 1
        for p, _, t in st.params:
            if t is not None:
                self.emit("typed(%s, %r, %r)" % (name(p), str(t), "Parameter '%s' of %s()" % (p, st.name)))
        self.level -= 1
        self.block(st.body)
        if st.returns is not None:
            self.level += 1
            self.emit("return typed(None, %r, %r)" % (str(st.returns), "The result of %s()" % st.name))
            self.level -= 1
        self.types.pop()
        self.returns.pop()
        self.emit("")

    def st_Return(self, st):
        value = "None" if st.value is None else self.expr(st.value)
        spec, fname = self.returns[-1] or (None, None)
        if spec is not None:
            value = "typed(%s, %r, %r)" % (value, str(spec), "The result of %s()" % fname)
        self.emit("return " + value)

    def st_Try(self, st):
        self.emit("try:")
        self.block(st.body)
        self.emit("except Exception as _err:")
        self.level += 1
        if st.err:
            self.emit("%s = error_record(_err)" % name(st.err))
        self.level -= 1
        self.block(st.handler)

    def st_Fail(self, st):
        self.emit("raise EchoError(show(%s), code='E407')" % self.expr(st.value))

    def st_Use(self, st):
        import os
        path = st.path[:-5] if st.path.endswith(".echo") else st.path
        mod = path.replace("/", ".").replace("\\", ".")
        alias = st.alias or os.path.basename(path)
        self.emit("import %s as %s  # convert %s to Python too" % (mod, name(alias), st.path))

    def st_Record(self, st):
        fields = [f for f, _, _ in st.fields]
        defaults = ", ".join("%r: lambda: %s" % (f, self.expr(d)) for f, d, _ in st.fields if d is not None)
        types = ", ".join("%r: %r" % (f, str(t)) for f, _, t in st.fields if t is not None)
        self.emit("%s = record(%r, %r, {%s}, {%s})" % (name(st.name), st.name, fields, defaults, types))

    def st_Global(self, st):
        self.emit("global " + ", ".join(name(n) for n in st.names))

    # ---- expressions ----
    def expr(self, e, store=False):
        return getattr(self, "ex_" + e.kind)(e, store) if e.kind in ("Attr",) else getattr(self, "ex_" + e.kind)(e)

    def ex_Num(self, e):
        return repr(e.value)

    def ex_Bool(self, e):
        return "True" if e.value else "False"

    def ex_Nothing(self, e):
        return "None"

    def ex_Str(self, e):
        if all(isinstance(p, str) for p in e.parts):
            return repr("".join(e.parts))
        out = [repr(p) if isinstance(p, str) else "show(%s)" % self.expr(p) for p in e.parts if p != ""]
        return "(" + " + ".join(out) + ")"

    def ex_List(self, e):
        return "[" + ", ".join(self.expr(x) for x in e.items) + "]"

    def ex_Map(self, e):
        return "{" + ", ".join("%s: %s" % (self.expr(k), self.expr(v)) for k, v in e.pairs) + "}"

    def ex_Name(self, e):
        return name(e.name)

    def ex_Lambda(self, e):
        return "(lambda %s: %s)" % (self.params(e.params), self.expr(e.body))

    def ex_Neg(self, e):
        return "(-%s)" % self.expr(e.expr)

    def ex_Not(self, e):
        if e.expr.kind in BOOLISH:
            return "(not %s)" % self.expr(e.expr)
        return "not_(%s)" % self.expr(e.expr)

    def ex_Logic(self, e):
        a, b = self.expr(e.left), self.expr(e.right)
        if e.op in ("and", "or"):
            if e.left.kind in BOOLISH and e.right.kind in BOOLISH:
                return "(%s %s %s)" % (a, e.op, b)
            return "%s_(%s, lambda: %s)" % (e.op, a, b)
        return "%s(%s, %s)" % (e.op, a, b)

    def ex_Compare(self, e):
        return "(%s %s %s)" % (self.expr(e.left), e.op, self.expr(e.right))

    def ex_BinOp(self, e):
        a, b = self.expr(e.left), self.expr(e.right)
        if e.op == "+":
            return "add(%s, %s)" % (a, b)
        if e.op == "/":
            return "div(%s, %s)" % (a, b)
        if e.op == "^":
            return "(%s ** %s)" % (a, b)
        return "(%s %s %s)" % (a, e.op, b)

    def ex_Index(self, e):
        return "%s[%s]" % (self.expr(e.obj), self.expr(e.index))

    def ex_Slice(self, e):
        return "%s[%s:%s]" % (self.expr(e.obj), self.expr(e.start) if e.start else "",
                              self.expr(e.stop) if e.stop else "")

    def ex_Attr(self, e, store=False):
        if e.obj.kind == "Name" and e.obj.name in MODULES and e.obj.name not in self.user_names:
            return "%s.%s" % (e.obj.name, e.name)
        if store:
            return "%s[%r]" % (self.expr(e.obj), e.name)
        return "attr(%s, %r)" % (self.expr(e.obj), e.name)

    def ex_Call(self, e):
        args = [self.expr(a) for a in e.args] + ["%s=%s" % (name(k), self.expr(v)) for k, v in e.kwargs]
        return "%s(%s)" % (self.expr(e.func), ", ".join(args))


def to_python(source):
    from .java import assigned_names
    build()
    tree = parse(source)
    g = PyGen(assigned_names(tree.body))
    g.types = [declared_types(tree.body)]
    g.emit("# Converted from Echo. Needs the echo package: pip install echo-lang (or this repo's python folder)")
    g.emit("from echo.pyruntime import *")
    g.emit("")
    for st in tree.body:
        g.stmt(st)
    return "\n".join(g.lines).replace("\n\n\n", "\n\n") + "\n"
