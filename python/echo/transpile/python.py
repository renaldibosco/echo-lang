"""Echo -> Python converter. Output runs with `pip install` of this package (it imports echo.pyruntime)."""
import keyword

from ..parser import parse

BOOLISH = {"Compare", "Bool"}
PY_RESERVED = set(keyword.kwlist) | {"print_", "self"}


def name(n):
    return n + "_" if n in PY_RESERVED else n


class PyGen:
    def __init__(self):
        self.lines = []
        self.level = 0
        self.tmp = 0

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
        target = self.expr(st.target, store=True)
        value = self.expr(st.value)
        if st.op == "=":
            self.emit("%s = %s" % (target, value))
        elif st.op == "+=":
            self.emit("%s = add(%s, %s)" % (target, target, value))
        elif st.op == "/=":
            self.emit("%s = div(%s, %s)" % (target, target, value))
        else:
            self.emit("%s %s %s" % (target, st.op, value))

    def st_Add(self, st):
        target = self.expr(st.target, store=True)
        self.emit("%s = add_to(%s, %s)" % (target, target, self.expr(st.value)))

    def st_Ask(self, st):
        if st.ai:
            call = "ai(show(%s))" % self.expr(st.prompt)
            self.emit("%s = %s" % (name(st.name), call) if st.name else "say(%s)" % call)
        else:
            self.emit("%s = ask(%s)" % (name(st.name), self.expr(st.prompt)))

    def st_If(self, st):
        for i, (cond, body) in enumerate(st.branches):
            self.emit("%s truthy(%s):" % ("if" if i == 0 else "elif", self.expr(cond)))
            self.block(body)
        if st.else_body is not None:
            self.emit("else:")
            self.block(st.else_body)

    def st_Repeat(self, st):
        self.emit("for _ in times(%s):" % self.expr(st.count))
        self.block(st.body)

    def st_While(self, st):
        self.emit("while truthy(%s):" % self.expr(st.cond))
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
        for pname, default in params:
            out.append(name(pname) if default is None else "%s=%s" % (name(pname), self.expr(default)))
        return ", ".join(out)

    def st_Define(self, st):
        self.emit("")
        self.emit("def %s(%s):" % (name(st.name), self.params(st.params)))
        self.block(st.body)
        self.emit("")

    def st_Return(self, st):
        self.emit("return" if st.value is None else "return " + self.expr(st.value))

    def st_Try(self, st):
        self.emit("try:")
        self.block(st.body)
        self.emit("except Exception as _err:")
        self.level += 1
        if st.err:
            self.emit("%s = message(_err)" % name(st.err))
        self.level -= 1
        self.block(st.handler)

    def st_Fail(self, st):
        self.emit("raise EchoError(show(%s))" % self.expr(st.value))

    def st_Use(self, st):
        if st.path.endswith(".echo"):
            mod = st.path[:-5].replace("/", ".").replace("\\", ".")
            self.emit("from %s import *  # convert %s to Python too" % (mod, st.path))

    def st_Record(self, st):
        fields = [f for f, _ in st.fields]
        defaults = ", ".join("%r: %s" % (f, self.expr(d)) for f, d in st.fields if d is not None)
        self.emit("%s = record(%r, %r, {%s})" % (name(st.name), st.name, fields, defaults))

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
        if store:
            return "%s[%r]" % (self.expr(e.obj), e.name)
        return "attr(%s, %r)" % (self.expr(e.obj), e.name)

    def ex_Call(self, e):
        args = [self.expr(a) for a in e.args] + ["%s=%s" % (name(k), self.expr(v)) for k, v in e.kwargs]
        return "%s(%s)" % (self.expr(e.func), ", ".join(args))


def to_python(source):
    tree = parse(source)
    g = PyGen()
    g.emit("# Converted from Echo. Needs the echo package: pip install echo-lang (or this repo's python folder)")
    g.emit("from echo.pyruntime import *")
    g.emit("")
    for st in tree.body:
        g.stmt(st)
    return "\n".join(g.lines).replace("\n\n\n", "\n\n") + "\n"
