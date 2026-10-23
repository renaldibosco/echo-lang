"""`echolang check`: finds mistakes without running the program.

It reports errors (unknown names, wrong number of values, type mismatches it can prove, unknown types) and
warnings (unused variables, unreachable code, values thrown away, names that hide built-ins).
"""
import difflib
import inspect

from .errors import CODES, EchoError
from .modules import GLOBALS, MODULES, build, old_name_hint
from .parser import TypeSpec, parse
from .values import BASE_TYPES, Builtin, Module, matches


class Diagnostic:
    def __init__(self, line, code, message, hint=None):
        self.line = line
        self.code = code
        self.message = message
        self.hint = hint

    @property
    def is_error(self):
        return self.code.startswith("E")

    def format(self, filename=None):
        where = "%s:%s" % (filename, self.line) if filename else "line %s" % self.line
        kind = "error" if self.is_error else "warning"
        text = "%s: %s %s: %s" % (where, kind, self.code, self.message)
        if self.hint:
            text += "\n    hint: " + self.hint
        return text

    def __repr__(self):
        return "<%s line %s: %s>" % (self.code, self.line, self.message)


TERMINATORS = {"Return", "Break", "Continue", "Fail"}


class Context:
    """One function body (or the top level)."""

    def __init__(self, parent=None, name=None, returns=None):
        self.parent = parent
        self.name = name
        self.returns = returns
        self.assigned = {}     # name -> first line
        self.types = {}        # name -> TypeSpec (declared)
        self.inferred = {}     # name -> type name when every assignment agrees
        self.read = set()
        self.loop_vars = set()
        self.params = set()

    def knows(self, name):
        c = self
        while c is not None:
            if name in c.assigned or name in c.params:
                return True
            c = c.parent
        return False

    def declared_type(self, name):
        c = self
        while c is not None:
            if name in c.types:
                return c.types[name]
            if name in c.assigned or name in c.params:
                return None
            c = c.parent
        return None


class Checker:
    def __init__(self):
        build()
        self.diags = []
        self.functions = {}    # top-level define name -> node
        self.records = {}      # record name -> node
        self.modules_used = {}  # alias -> path

    def add(self, line, code, message, hint=None):
        self.diags.append(Diagnostic(line, code, message, hint))

    # ---------------------------------------------------------------- entry
    def check(self, source):
        try:
            tree = parse(source)
        except EchoError as e:
            self.add(e.line, e.code, e.message, e.hint)
            return self.diags
        for st in tree.body:
            if st.kind == "Define":
                self.functions[st.name] = st
            elif st.kind == "Record":
                self.records[st.name] = st
        top = Context()
        self.collect(tree.body, top)
        self.block(tree.body, top)
        self.unused(top, top_level=True)
        self.diags.sort(key=lambda d: (d.line or 0, d.code))
        return self.diags

    # ---------------------------------------------------------------- collecting names
    def collect(self, body, ctx):
        for st in body:
            k = st.kind
            if k == "Set" and st.target.kind == "Name":
                ctx.assigned.setdefault(st.target.name, st.line)
                if st.type is not None:
                    ctx.types[st.target.name] = st.type
            elif k == "Ask":
                ctx.assigned.setdefault(st.name, st.line)
            elif k == "ForEach":
                for v in (st.var, st.var2):
                    if v:
                        ctx.assigned.setdefault(v, st.line)
                        ctx.loop_vars.add(v)
            elif k == "ForRange":
                ctx.assigned.setdefault(st.var, st.line)
                ctx.loop_vars.add(st.var)
            elif k in ("Define", "Record"):
                ctx.assigned.setdefault(st.name, st.line)
                ctx.read.add(st.name)  # functions and records are not "unused variables"
            elif k == "Use":
                import os
                alias = st.alias or os.path.splitext(os.path.basename(st.path))[0]
                ctx.assigned.setdefault(alias, st.line)
                ctx.read.add(alias)
            elif k == "Try" and st.err:
                ctx.assigned.setdefault(st.err, st.line)
                ctx.read.add(st.err)
            elif k == "Global":
                for n in st.names:
                    ctx.read.add(n)
            for sub in self.sub_blocks(st):
                self.collect(sub, ctx)

    @staticmethod
    def sub_blocks(st):
        if st.kind == "If":
            out = [b for _, b in st.branches]
            if st.else_body:
                out.append(st.else_body)
            return out
        if st.kind in ("Repeat", "While", "ForEach", "ForRange"):
            return [st.body]
        if st.kind == "Try":
            return [st.body, st.handler]
        return []

    # ---------------------------------------------------------------- statements
    def block(self, body, ctx):
        dead_reported = False
        for i, st in enumerate(body):
            if i > 0 and body[i - 1].kind in TERMINATORS and not dead_reported:
                self.add(st.line, "W102", "This line never runs (it comes after %s)."
                         % body[i - 1].kind.lower())
                dead_reported = True
            self.statement(st, ctx)

    def statement(self, st, ctx):
        k = st.kind
        if k == "Set":
            vtype = self.expr(st.value, ctx)
            if st.target.kind == "Name":
                name = st.target.name
                if name in GLOBALS or name in MODULES:
                    if not (ctx.parent is None and name in self.functions):
                        self.add(st.line, "W104", "'%s' hides the built-in %s of the same name."
                                 % (name, "module" if name in MODULES else "function"),
                                 "Choose another name, e.g. my_%s." % name)
                if st.type is not None:
                    self.validate_type(st.type, st.line)
                    self.type_mismatch(st.value, vtype, st.type, "Variable '%s'" % name, st.line)
                else:
                    declared = ctx.declared_type(name)
                    if declared is not None:
                        self.type_mismatch(st.value, vtype, declared, "Variable '%s'" % name, st.line)
                prev = ctx.inferred.get(name, vtype)
                ctx.inferred[name] = vtype if prev == vtype else None
            else:
                self.expr(st.target, ctx, store=True)
        elif k == "Add":
            self.expr(st.value, ctx)
            t = self.expr(st.target, ctx)
            if t is not None and t != "list":
                self.add(st.line, "E301", "'add ... to' needs a list, not %s." % t,
                         "For numbers write: set total to total + value")
        elif k == "Say":
            for v in st.values:
                self.expr(v, ctx)
        elif k == "Ask":
            self.expr(st.prompt, ctx)
        elif k == "ExprStmt":
            self.expr(st.expr, ctx)
            if st.expr.kind != "Call":
                self.add(st.line, "W103", "This line computes a value and throws it away.",
                         "Did you mean: say ...  or  set name to ...?")
        elif k == "If":
            for cond, body in st.branches:
                self.condition(cond, ctx, "if")
                self.block(body, ctx)
            if st.else_body is not None:
                self.block(st.else_body, ctx)
        elif k == "While":
            self.condition(st.cond, ctx, "while")
            self.block(st.body, ctx)
        elif k == "Repeat":
            t = self.expr(st.count, ctx)
            if t not in (None, "number", "integer"):
                self.add(st.line, "E301", "repeat needs a number of times, not %s." % t)
            self.block(st.body, ctx)
        elif k == "ForEach":
            t = self.expr(st.iterable, ctx)
            if t in ("number", "integer", "boolean", "nothing", "function"):
                self.add(st.line, "E301", "Can't loop over %s." % t,
                         "For numbers write: for i from 1 to n")
            self.block(st.body, ctx)
        elif k == "ForRange":
            for part in (st.start, st.stop, st.step):
                if part is not None:
                    t = self.expr(part, ctx)
                    if t not in (None, "number", "integer"):
                        self.add(st.line, "E301", "Loop bounds must be numbers, not %s." % t)
            self.block(st.body, ctx)
        elif k == "Define":
            self.define(st, ctx)
        elif k == "Return":
            if st.value is not None:
                t = self.expr(st.value, ctx)
                if ctx.returns is not None:
                    self.type_mismatch(st.value, t, ctx.returns, "The result of %s()" % ctx.name, st.line)
            elif ctx.returns is not None and not ctx.returns.optional and ctx.returns.name not in ("nothing", "any"):
                self.add(st.line, "E302", "%s() must return %s, but this return gives nothing."
                         % (ctx.name, ctx.returns))
        elif k == "Try":
            self.block(st.body, ctx)
            self.block(st.handler, ctx)
        elif k == "Fail":
            self.expr(st.value, ctx)
        elif k == "Record":
            for _, default, ftype in st.fields:
                if ftype is not None:
                    self.validate_type(ftype, st.line)
                if default is not None:
                    t = self.expr(default, ctx)
                    if ftype is not None:
                        self.type_mismatch(default, t, ftype, "The default of a field in %s" % st.name, st.line)

    def define(self, st, outer):
        ctx = Context(outer, st.name, st.returns)
        for pname, default, ptype in st.params:
            ctx.params.add(pname)
            if ptype is not None:
                self.validate_type(ptype, st.line)
                ctx.types[pname] = ptype
            if default is not None:
                t = self.expr(default, outer)
                if ptype is not None:
                    self.type_mismatch(default, t, ptype, "The default of '%s'" % pname, st.line)
        if st.returns is not None:
            self.validate_type(st.returns, st.line)
        self.collect(st.body, ctx)
        self.block(st.body, ctx)
        if st.returns is not None and st.returns.name not in ("nothing", "any") and not st.returns.optional:
            if not self.always_returns(st.body):
                self.add(st.line, "W105", "%s() says it returns %s, but some paths end without return."
                         % (st.name, st.returns))
        self.unused(ctx)

    def always_returns(self, body):
        for st in body:
            if st.kind in ("Return", "Fail"):
                return True
            if st.kind == "If" and st.else_body is not None:
                if all(self.always_returns(b) for _, b in st.branches) and self.always_returns(st.else_body):
                    return True
            if st.kind == "Try" and self.always_returns(st.body) and self.always_returns(st.handler):
                return True
        return False

    def unused(self, ctx, top_level=False):
        for name, line in sorted(ctx.assigned.items(), key=lambda x: x[1]):
            if name in ctx.read or name.startswith("_") or name in ctx.loop_vars:
                continue
            if top_level:
                continue  # top-level variables may be used by files that `use` this one
            self.add(line, "W101", "'%s' is set but never used." % name)

    # ---------------------------------------------------------------- types
    def validate_type(self, spec, line):
        while spec is not None:
            if spec.name not in BASE_TYPES and spec.name not in self.records:
                close = difflib.get_close_matches(spec.name, list(BASE_TYPES) + list(self.records), n=1)
                self.add(spec.line or line, "E304", "Unknown type '%s'." % spec.name,
                         "Did you mean '%s'?" % close[0] if close else None)
                return
            spec = spec.of

    def type_mismatch(self, node, inferred, spec, what, line):
        if spec is None or inferred is None or spec.name == "any":
            return
        if spec.name not in BASE_TYPES and spec.name not in self.records:
            return  # already reported as E304
        if node is not None and node.kind in ("Num", "Str", "Bool", "Nothing") and spec.name not in self.records:
            value = self.literal(node)
            if value is not _UNKNOWN:
                if not matches(value, spec):
                    self.add(line, "E302", "%s must be %s, but this is %s." % (what, spec, self.describe(node)))
                return
        if not self.compatible(inferred, spec):
            self.add(line, "E302", "%s must be %s, but this is %s." % (what, spec, inferred))

    def compatible(self, inferred, spec):
        if inferred == "nothing":
            return spec.optional or spec.name in ("nothing", "any")
        want = spec.name
        if want in ("dna", "rna", "protein"):
            return inferred in ("text", want)
        if want == "integer":
            return inferred in ("number", "integer")
        if want == "number":
            return inferred in ("number", "integer")
        if want in self.records:
            return inferred == want or inferred == "map"
        return inferred == want

    @staticmethod
    def literal(node):
        if node.kind == "Num":
            return node.value
        if node.kind == "Bool":
            return node.value
        if node.kind == "Nothing":
            return None
        if node.kind == "Str" and all(isinstance(p, str) for p in node.parts):
            return "".join(node.parts)
        return _UNKNOWN

    def describe(self, node):
        v = self.literal(node)
        if node.kind == "Str":
            return 'text "%s"' % (v if len(v) < 20 else v[:17] + "...")
        if node.kind == "Num":
            return "number %s" % node.value
        if node.kind == "Bool":
            return "boolean"
        return "nothing"

    def condition(self, node, ctx, word):
        t = self.expr(node, ctx)
        if t is not None and t != "boolean":
            shown = "a number" if t in ("number", "integer") else ("text" if t == "text" else "a " + t)
            self.add(node.line, "E303", "The %s condition is %s, but it must be true or false." % (word, shown),
                     "Compare it, e.g. %s count > 0%s" % (word, " then" if word == "if" else ""))

    # ---------------------------------------------------------------- expressions (return an inferred type or None)
    def expr(self, e, ctx, store=False):
        k = e.kind
        if k == "Num":
            return "integer" if isinstance(e.value, int) else "number"
        if k == "Str":
            for p in e.parts:
                if not isinstance(p, str):
                    self.expr(p, ctx)
            return "text"
        if k == "Bool":
            return "boolean"
        if k == "Nothing":
            return "nothing"
        if k == "List":
            for x in e.items:
                self.expr(x, ctx)
            return "list"
        if k == "Map":
            for a, b in e.pairs:
                self.expr(a, ctx)
                self.expr(b, ctx)
            return "map"
        if k == "Name":
            return self.name(e, ctx)
        if k == "Lambda":
            inner = Context(ctx, "fn")
            for pname, default, ptype in e.params:
                inner.params.add(pname)
                if ptype is not None:
                    inner.types[pname] = ptype
            self.expr(e.body, inner)
            return "function"
        if k == "Neg":
            t = self.expr(e.expr, ctx)
            if t not in (None, "number", "integer"):
                self.add(e.line, "E301", "Can't make %s negative." % t)
            return t
        if k == "Not":
            t = self.expr(e.expr, ctx)
            if t not in (None, "boolean", "integer"):
                self.add(e.line, "E301", "'not' needs true/false or a bit, not %s." % t)
            return t
        if k == "Logic":
            a, b = self.expr(e.left, ctx), self.expr(e.right, ctx)
            for t in (a, b):
                if t not in (None, "boolean", "integer"):
                    self.add(e.line, "E301", "'%s' needs true/false or bits (0 or 1), not %s." % (e.op, t))
                    return None
            return "boolean" if "boolean" in (a, b) else (a or b)
        if k == "Compare":
            a, b = self.expr(e.left, ctx), self.expr(e.right, ctx)
            if e.op in ("<", ">", "<=", ">="):
                nums = ("number", "integer")
                if a and b and not ((a in nums and b in nums) or (a == b == "text")):
                    self.add(e.line, "E301", "Can't compare %s with %s using %s." % (a, b, e.op))
            return "boolean"
        if k == "BinOp":
            a, b = self.expr(e.left, ctx), self.expr(e.right, ctx)
            nums = ("number", "integer")
            if e.op == "+":
                if "text" in (a, b):
                    return "text"
                if a in nums and b in nums:
                    return "integer" if a == b == "integer" else "number"
                if a == b == "list":
                    return "list"
                if a and b and a != b and not (a in nums and b in nums):
                    self.add(e.line, "E301", "Can't add %s and %s." % (a, b))
                return None
            if e.op == "*":
                if a in nums and b in nums:
                    return "integer" if a == b == "integer" else "number"
                return None
            for t in (a, b):
                if t is not None and t not in nums:
                    self.add(e.line, "E301", "'%s' needs two numbers, not %s." % (e.op, t))
                    return None
            if a and b:
                return "integer" if e.op in ("//", "%", "-") and a == b == "integer" else "number"
            return None
        if k == "Index":
            self.expr(e.obj, ctx)
            self.expr(e.index, ctx)
            return None
        if k == "Slice":
            t = self.expr(e.obj, ctx)
            for p in (e.start, e.stop):
                if p is not None:
                    self.expr(p, ctx)
            return t if t in ("text", "list") else None
        if k == "Attr":
            return self.attr(e, ctx)
        if k == "Call":
            return self.call(e, ctx)
        return None

    def name(self, e, ctx):
        n = e.name
        c = ctx
        while c is not None:
            if n in c.assigned or n in c.params:
                c.read.add(n)
                break
            c = c.parent
        if ctx.knows(n):
            declared = ctx.declared_type(n)
            if declared is not None:
                return None if declared.optional else declared.name
            if n in self.records and not ctx.parent:
                return "function"
            c = ctx
            while c is not None:
                if n in c.assigned or n in c.params:
                    return c.inferred.get(n)
                c = c.parent
            return None
        if n in GLOBALS:
            return "function" if isinstance(GLOBALS[n], Builtin) else None
        if n in MODULES:
            return "module"
        hint = old_name_hint(n)
        if not hint:
            names = set(GLOBALS) | set(MODULES)
            c = ctx
            while c is not None:
                names.update(c.assigned)
                names.update(c.params)
                c = c.parent
            close = difflib.get_close_matches(n, list(names), n=1, cutoff=0.75)
            hint = "Did you mean '%s'?" % close[0] if close else "Set it first: set %s to ..." % n
        self.add(e.line, "E201", "Unknown name '%s'." % n, hint)
        return None

    def attr(self, e, ctx):
        obj = e.obj
        if obj.kind == "Name" and obj.name in MODULES and not ctx.knows(obj.name):
            mod = MODULES[obj.name]
            if e.name not in mod.members:
                close = difflib.get_close_matches(e.name, list(mod.members), n=1, cutoff=0.6)
                self.add(e.line, "E202", "Module %s has no '%s'." % (obj.name, e.name),
                         "Did you mean %s.%s?" % (obj.name, close[0]) if close else 'See help("%s").' % obj.name)
                return None
            value = mod.members[e.name]
            if isinstance(value, Builtin):
                return "function"
            return _type_of_constant(value)
        t = self.expr(obj, ctx)
        if t in self.records:
            fields = [f[0] for f in self.records[t].fields]
            if e.name not in fields:
                self.add(e.line, "E202", "Record %s has no field '%s'." % (t, e.name), "Fields: " + ", ".join(fields))
                return None
            ftype = next(f[2] for f in self.records[t].fields if f[0] == e.name)
            return ftype.name if ftype is not None and ftype.of is None and not ftype.optional else None
        if t in ("number", "integer", "text", "boolean", "list", "nothing"):
            self.add(e.line, "E202", "%s has no field '%s'." % (t.capitalize(), e.name),
                     "Echo has no method calls on values; call a function instead, e.g. upper(name).")
        return None

    def call(self, e, ctx):
        f = e.func
        for a in e.args:
            self.expr(a, ctx)
        for _, v in e.kwargs:
            self.expr(v, ctx)
        target = None
        if f.kind == "Name" and not self.shadowed(f.name, ctx):
            self.expr(f, ctx)
            if f.name in self.functions:
                return self.check_user_call(self.functions[f.name], e)
            if f.name in self.records:
                self.check_params(f.name, [(n, d) for n, d, _ in self.records[f.name].fields], e, "field")
                self.check_record_types(self.records[f.name], e, ctx)
                return f.name
            target = GLOBALS.get(f.name)
        elif f.kind == "Attr" and f.obj.kind == "Name" and f.obj.name in MODULES and not ctx.knows(f.obj.name):
            if self.attr(f, ctx) is None:
                return None
            target = MODULES[f.obj.name].members.get(f.name)
        else:
            t = self.expr(f, ctx)
            if t in ("number", "integer", "text", "boolean", "list", "map", "nothing"):
                self.add(e.line, "E206", "This is %s, not a function, so it can't be called." % t)
            return None
        if isinstance(target, Builtin):
            self.check_builtin_call(target, e)
        return None

    def shadowed(self, name, ctx):
        return ctx.knows(name) and name not in self.functions and name not in self.records

    def check_user_call(self, d, e):
        self.check_params(d.name, [(n, df) for n, df, _ in d.params], e, "parameter")
        for (pname, _, ptype), arg in zip(d.params, e.args):
            if ptype is not None:
                self.type_mismatch(arg, self.expr_type_quiet(arg), ptype,
                                   "Parameter '%s' of %s()" % (pname, d.name), e.line)
        kw = dict(e.kwargs)
        for pname, _, ptype in d.params:
            if pname in kw and ptype is not None:
                self.type_mismatch(kw[pname], self.expr_type_quiet(kw[pname]), ptype,
                                   "Parameter '%s' of %s()" % (pname, d.name), e.line)
        if d.returns is not None and d.returns.of is None and not d.returns.optional:
            return d.returns.name
        return None

    def check_record_types(self, rec, e, ctx):
        for (fname, _, ftype), arg in zip(rec.fields, e.args):
            if ftype is not None:
                self.type_mismatch(arg, self.expr_type_quiet(arg), ftype, "Field %s.%s" % (rec.name, fname), e.line)

    def expr_type_quiet(self, node):
        """Type of a literal-ish node without re-reporting problems."""
        return {"Num": "integer" if node.kind == "Num" and isinstance(getattr(node, "value", 0), int) else "number",
                "Str": "text", "Bool": "boolean", "Nothing": "nothing", "List": "list", "Map": "map"}.get(node.kind)

    def check_params(self, name, params, e, what):
        names = [p[0] for p in params]
        if len(e.args) > len(params):
            self.add(e.line, "E203", "%s() takes %d value%s but gets %d." % (
                name, len(params), "" if len(params) == 1 else "s", len(e.args)))
            return
        given = set(names[:len(e.args)])
        for k, _ in e.kwargs:
            if k not in names:
                close = difflib.get_close_matches(k, names, n=1)
                self.add(e.line, "E204", "%s() has no %s called '%s'." % (name, what, k),
                         "Did you mean '%s'?" % close[0] if close else "It has: " + ", ".join(names))
            elif k in given:
                self.add(e.line, "E203", "%s() gets '%s' twice." % (name, k))
            given.add(k)
        for pname, default in params:
            if default is None and pname not in given:
                self.add(e.line, "E205", "%s() is missing the value for '%s'." % (name, pname))

    def check_builtin_call(self, b, e):
        try:
            sig = inspect.signature(b.fn)
        except (TypeError, ValueError):
            return
        params = list(sig.parameters.values())
        if b.needs_interp:
            params = params[1:]
        try:
            fake = inspect.Signature(params)
            fake.bind(*range(len(e.args)), **{k: 0 for k, _ in e.kwargs})
        except TypeError as err:
            msg = str(err)
            if "unexpected keyword" in msg or "got an unexpected" in msg:
                bad = next((k for k, _ in e.kwargs if k not in sig.parameters), "?")
                self.add(e.line, "E204", "%s() has no setting called '%s'." % (b.qualname, bad), b.doc or None)
            else:
                self.add(e.line, "E203", "Wrong number of values for %s()." % b.qualname, b.doc or None)


class _Unknown:
    pass


_UNKNOWN = _Unknown()


def _type_of_constant(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, list):
        return "list"
    if isinstance(v, Module):
        return "module"
    return None


def check_source(source):
    """List of Diagnostic objects (errors first by line)."""
    return Checker().check(source)


def explain_code(code):
    from .errors import explain
    return explain(code)


__all__ = ["check_source", "Diagnostic", "CODES", "explain_code"]
