"""Echo -> Java converter. The output uses echo.EchoRuntime (copy it with: echolang java --runtime DIR)."""
from ..errors import EchoSyntaxError
from ..parser import parse
from ..stdlib import load

JAVA_RESERVED = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
    "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
    "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false", "null", "var", "record",
    "yield", "sealed", "permits", "String", "Object", "Math", "System", "List", "Map", "main", "run",
}
RUNTIME_NAME_FIX = {"int": "int_"}
CONSTANTS = {"pi", "e", "start_codon", "stop_codons"}


def jname(n):
    return n + "_" if n in JAVA_RESERVED else n


def jstring(s):
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 32:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def assigned_names(body, out=None, globals_=None):
    """Names a block assigns (not inside nested functions)."""
    out = out if out is not None else []
    globals_ = globals_ if globals_ is not None else set()

    def add(n):
        if n not in out:
            out.append(n)

    for st in body:
        k = st.kind
        if k == "Set" and st.target.kind == "Name":
            add(st.target.name)
        elif k == "Add" and st.target.kind == "Name":
            add(st.target.name)
        elif k == "Ask" and st.name:
            add(st.name)
        elif k == "ForEach":
            add(st.var)
            if st.var2:
                add(st.var2)
        elif k == "ForRange":
            add(st.var)
        elif k == "Record":
            add(st.name)
        elif k == "Global":
            globals_.update(st.names)
        if k == "If":
            for _, b in st.branches:
                assigned_names(b, out, globals_)
            if st.else_body:
                assigned_names(st.else_body, out, globals_)
        elif k in ("Repeat", "While", "ForEach", "ForRange"):
            assigned_names(st.body, out, globals_)
        elif k == "Try":
            if st.err:
                add(st.err)
            assigned_names(st.body, out, globals_)
            assigned_names(st.handler, out, globals_)
    return out


def free_names(expr, found):
    """All Name references inside an expression tree."""
    if expr is None:
        return found
    if isinstance(expr, list):
        for x in expr:
            free_names(x, found)
        return found
    if isinstance(expr, tuple):
        for x in expr:
            free_names(x, found)
        return found
    if not hasattr(expr, "kind"):
        return found
    if expr.kind == "Name":
        found.add(expr.name)
    for k, v in expr.__dict__.items():
        if k in ("kind", "line"):
            continue
        if isinstance(v, (list, tuple)) or hasattr(v, "kind"):
            free_names(v, found)
    return found


class JavaGen:
    def __init__(self, class_name):
        self.cls = class_name
        self.out = []
        self.level = 0
        self.tmp = 0
        self.functions = {}     # name -> Define node
        self.globals = []
        self.ctx = None         # current function context
        self.builtins = load()

    def emit(self, text):
        self.out.append("    " * self.level + text)

    def new_tmp(self, prefix="_t"):
        self.tmp += 1
        return "%s%d" % (prefix, self.tmp)

    # ---- program ----
    def program(self, tree):
        top = []
        for st in tree.body:
            if st.kind == "Define":
                if st.name in self.functions:
                    raise EchoSyntaxError("Java: function '%s' is defined twice." % st.name, st.line)
                self.functions[st.name] = st
            else:
                top.append(st)
        self.check_nested(tree.body)
        self.globals = [n for n in assigned_names(top) if n not in self.functions]
        for f in self.functions.values():
            g = set()
            assigned_names(f.body, [], g)
            for n in g:
                if n not in self.globals:
                    self.globals.append(n)

        self.emit("// Converted from Echo. Compile together with echo/EchoRuntime.java:")
        self.emit("//   javac -d out %s.java echo/EchoRuntime.java && java -cp out %s" % (self.cls, self.cls))
        self.emit("import echo.EchoRuntime.EchoFn;")
        self.emit("import static echo.EchoRuntime.*;")
        self.emit("")
        self.emit("public class %s {" % self.cls)
        self.level += 1
        for g in self.globals:
            self.emit("static Object %s = null;" % jname(g))
        if self.globals:
            self.emit("")
        for f in self.functions.values():
            self.function(f)
        self.emit("public static void main(String[] args) {")
        self.level += 1
        self.emit("try {")
        self.level += 1
        self.emit("run();")
        self.level -= 1
        self.emit("} catch (EchoError err) {")
        self.emit("    System.err.println(err.getMessage());")
        self.emit("    System.exit(1);")
        self.emit("}")
        self.level -= 1
        self.emit("}")
        self.emit("")
        self.emit("/** The program itself. Android apps can call " + self.cls + ".run() on a background thread. */")
        self.emit("public static void run() {")
        self.ctx = {"locals": set(), "lambda": None, "global_decl": set()}
        self.body(top)
        self.ctx = None
        self.emit("}")
        self.level -= 1
        self.emit("}")
        return "\n".join(self.out) + "\n"

    def check_nested(self, body, depth=0):
        for st in body:
            if st.kind == "Define" and depth > 0:
                raise EchoSyntaxError("Java: put 'define %s' at the top level, not inside another block." % st.name,
                                      st.line)
            for attr in ("body", "else_body", "handler"):
                sub = getattr(st, attr, None)
                if isinstance(sub, list):
                    self.check_nested(sub, depth + 1)
            if st.kind == "If":
                for _, b in st.branches:
                    self.check_nested(b, depth + 1)

    def function(self, f):
        params = [p for p, _ in f.params]
        g = set()
        locs = [n for n in assigned_names(f.body, [], g) if n not in params and n not in g]
        self.emit("static Object %s(%s) {" % (jname(f.name), ", ".join("Object " + jname(p) for p in params)))
        self.level += 1
        if locs:
            self.emit("Object " + ", ".join("%s = null" % jname(n) for n in locs) + ";")
        self.ctx = {"locals": set(params) | set(locs), "lambda": None, "global_decl": g}
        self.emit("if (true) {")
        self.body(f.body, indent=True)
        self.emit("}")
        self.emit("return null;")
        self.ctx = None
        self.level -= 1
        self.emit("}")
        self.emit("")

    def body(self, stmts, indent=True):
        if indent:
            self.level += 1
        for st in stmts:
            getattr(self, "st_" + st.kind)(st)
        if indent:
            self.level -= 1

    # ---- statements ----
    def st_ExprStmt(self, st):
        self.emit("discard(%s);" % self.expr(st.expr))

    def st_Pass(self, st):
        pass

    def st_Say(self, st):
        self.emit("say(%s);" % ", ".join(self.expr(v) for v in st.values))

    def store(self, target, value):
        if target.kind == "Name":
            return "%s = %s;" % (self.var(target.name, target.line, store=True), value)
        if target.kind == "Index":
            return "setIndex(%s, %s, %s);" % (self.expr(target.obj), self.expr(target.index), value)
        return "setAttr(%s, %s, %s);" % (self.expr(target.obj), jstring(target.name), value)

    def st_Set(self, st):
        value = self.expr(st.value)
        if st.op != "=":
            fn = {"+=": "add", "-=": "sub", "*=": "mul", "/=": "div"}[st.op]
            value = "%s(%s, %s)" % (fn, self.expr(st.target), value)
        self.emit(self.store(st.target, value))

    def st_Add(self, st):
        self.emit(self.store(st.target, "addTo(%s, %s)" % (self.expr(st.target), self.expr(st.value))))

    def st_Ask(self, st):
        if st.ai:
            call = "ai(show(%s))" % self.expr(st.prompt)
            if st.name:
                self.emit("%s = %s;" % (self.var(st.name, st.line, True), call))
            else:
                self.emit("say(%s);" % call)
        else:
            self.emit("%s = ask(%s);" % (self.var(st.name, st.line, True), self.expr(st.prompt)))

    def cond(self, e):
        if e.kind == "Compare":
            return self.compare(e)
        if e.kind == "Bool":
            return "true" if e.value else "false"
        return "truthy(%s)" % self.expr(e)

    def st_If(self, st):
        for i, (c, b) in enumerate(st.branches):
            self.emit("%sif (%s) {" % ("" if i == 0 else "} else ", self.cond(c)))
            self.body(b)
        if st.else_body is not None:
            self.emit("} else {")
            self.body(st.else_body)
        self.emit("}")

    def st_Repeat(self, st):
        i, n = self.new_tmp("_i"), self.new_tmp("_n")
        self.emit("for (long %s = 0, %s = toLong(%s); %s < %s; %s++) {" % (i, n, self.expr(st.count), i, n, i))
        self.body(st.body)
        self.emit("}")

    def st_While(self, st):
        c = "truthy(%s)" % self.expr(st.cond) if st.cond.kind == "Bool" else self.cond(st.cond)
        self.emit("while (%s) {" % c)
        self.body(st.body)
        self.emit("}")

    def st_ForEach(self, st):
        it = self.new_tmp("_it")
        if st.var2:
            self.emit("for (Object[] %s : pairs(%s)) {" % (it, self.expr(st.iterable)))
            self.level += 1
            self.emit("%s = %s[0];" % (self.var(st.var, st.line, True), it))
            self.emit("%s = %s[1];" % (self.var(st.var2, st.line, True), it))
            self.level -= 1
        else:
            self.emit("for (Object %s : iter(%s)) {" % (it, self.expr(st.iterable)))
            self.level += 1
            self.emit("%s = %s;" % (self.var(st.var, st.line, True), it))
            self.level -= 1
        self.body(st.body)
        self.emit("}")

    def st_ForRange(self, st):
        it = self.new_tmp("_it")
        step = self.expr(st.step) if st.step is not None else "null"
        self.emit("for (Object %s : loopRange(%s, %s, %s)) {" % (it, self.expr(st.start), self.expr(st.stop), step))
        self.level += 1
        self.emit("%s = %s;" % (self.var(st.var, st.line, True), it))
        self.level -= 1
        self.body(st.body)
        self.emit("}")

    def st_Break(self, st):
        self.emit("if (true) break;")

    def st_Continue(self, st):
        self.emit("if (true) continue;")

    def st_Return(self, st):
        self.emit("if (true) return %s;" % (self.expr(st.value) if st.value is not None else "null"))

    def st_Define(self, st):
        raise EchoSyntaxError("Java: put 'define %s' at the top level." % st.name, st.line)

    def st_Try(self, st):
        err = self.new_tmp("_e")
        self.emit("try {")
        self.body(st.body)
        self.emit("} catch (RuntimeException | StackOverflowError %s) {" % err)
        self.level += 1
        if st.err:
            self.emit("%s = message(%s);" % (self.var(st.err, st.line, True), err))
        self.level -= 1
        self.body(st.handler)
        self.emit("}")

    def st_Fail(self, st):
        self.emit("if (true) throw new EchoError(show(%s));" % self.expr(st.value))

    def st_Use(self, st):
        self.emit("// use %s  (convert that file too and call its run())" % st.path)

    def st_Record(self, st):
        fields = "new String[]{%s}" % ", ".join(jstring(f) for f, _ in st.fields)
        defaults = "new Object[]{%s}" % ", ".join(self.expr(d) if d is not None else "null" for _, d in st.fields)
        self.emit("%s = record(%s, %s, %s);" % (self.var(st.name, st.line, True), jstring(st.name), fields, defaults))

    def st_Global(self, st):
        pass

    # ---- names ----
    def var(self, n, line, store=False):
        ctx = self.ctx
        lam = ctx["lambda"] if ctx else None
        if lam is not None:
            if n in lam["params"]:
                return lam["params"][n]
            if n in lam["captured"]:
                return "%s[%d]" % (lam["c"], lam["captured"][n])
            if store:
                raise EchoSyntaxError("Java: a fn(...) -> ... can't change variables.", line)
        if ctx and n in ctx["locals"] and n not in ctx["global_decl"]:
            return jname(n)
        if n in self.globals:
            return "%s.%s" % (self.cls, jname(n)) if lam is not None else jname(n)
        if store:
            return jname(n)
        if n in self.functions:
            f = self.functions[n]
            a = self.new_tmp("_f")
            args = ", ".join("arg(%s, %d)" % (a, i) for i in range(len(f.params)))
            return "named(%s, %s -> %s.%s(%s))" % (jstring(n), a, self.cls, jname(n), args)
        if n in CONSTANTS:
            return n
        if n in self.builtins:
            return "fn(%s)" % jstring(n)
        raise EchoSyntaxError("I don't know '%s'." % n, line, "Set it first: set %s to ..." % n)

    # ---- expressions ----
    def expr(self, e):
        return getattr(self, "ex_" + e.kind)(e)

    def ex_Num(self, e):
        if isinstance(e.value, int):
            return "%dL" % e.value
        return repr(float(e.value))

    def ex_Bool(self, e):
        return "true" if e.value else "false"

    def ex_Nothing(self, e):
        return "null"

    def ex_Str(self, e):
        if all(isinstance(p, str) for p in e.parts):
            return jstring("".join(e.parts))
        return "str(%s)" % ", ".join(jstring(p) if isinstance(p, str) else self.expr(p) for p in e.parts if p != "")

    def ex_List(self, e):
        return "list(%s)" % ", ".join(self.expr(x) for x in e.items)

    def ex_Map(self, e):
        return "map(%s)" % ", ".join("%s, %s" % (self.expr(k), self.expr(v)) for k, v in e.pairs)

    def ex_Name(self, e):
        return self.var(e.name, e.line)

    def ex_Lambda(self, e):
        outer = self.ctx or {"locals": set(), "lambda": None, "global_decl": set()}
        lid = self.new_tmp("")
        params = {p: "p%s_%s" % (lid, p) for p, _ in e.params}
        free = free_names(e.body, set()) - set(params)
        outer_lam = outer["lambda"]
        captured, cap_exprs = {}, []
        for n in sorted(free):
            local_here = (n in outer["locals"] and n not in outer["global_decl"]) or \
                         (outer_lam is not None and (n in outer_lam["params"] or n in outer_lam["captured"]))
            if local_here:
                captured[n] = len(cap_exprs)
                cap_exprs.append(self.var(n, e.line))
        lam = {"params": params, "captured": captured, "c": "_c" + lid, "a": "_a" + lid}
        saved = self.ctx
        self.ctx = {"locals": outer["locals"], "lambda": lam, "global_decl": outer["global_decl"]}
        body = self.expr(e.body)
        self.ctx = saved
        unpack = "".join("Object %s = arg(%s, %d); " % (v, lam["a"], i) for i, v in enumerate(params.values()))
        fn_text = "(EchoFn) %s -> { %sreturn %s; }" % (lam["a"], unpack, body)
        if cap_exprs:
            return "capture(new Object[]{%s}, %s -> %s)" % (", ".join(cap_exprs), lam["c"], fn_text)
        return "(%s)" % fn_text

    def ex_Neg(self, e):
        return "neg(%s)" % self.expr(e.expr)

    def ex_Not(self, e):
        return "not(%s)" % self.expr(e.expr)

    def ex_Logic(self, e):
        boolish = ("Compare", "Bool")
        if e.op in ("and", "or") and e.left.kind in boolish and e.right.kind in boolish:
            return "(%s %s %s)" % (self.cond(e.left), "&&" if e.op == "and" else "||", self.cond(e.right))
        return "%s(%s, %s)" % (e.op, self.expr(e.left), self.expr(e.right))

    def compare(self, e):
        a, b = self.expr(e.left), self.expr(e.right)
        fn = {"==": "eq", "!=": "ne", "<": "lt", ">": "gt", "<=": "le", ">=": "ge", "in": "in"}.get(e.op)
        if e.op == "not in":
            return "!in(%s, %s)" % (a, b)
        return "%s(%s, %s)" % (fn, a, b)

    def ex_Compare(self, e):
        return self.compare(e)

    def ex_BinOp(self, e):
        fn = {"+": "add", "-": "sub", "*": "mul", "/": "div", "//": "floordiv", "%": "mod", "^": "pow"}[e.op]
        return "%s(%s, %s)" % (fn, self.expr(e.left), self.expr(e.right))

    def ex_Index(self, e):
        return "index(%s, %s)" % (self.expr(e.obj), self.expr(e.index))

    def ex_Slice(self, e):
        return "slice(%s, %s, %s)" % (self.expr(e.obj), self.expr(e.start) if e.start else "null",
                                     self.expr(e.stop) if e.stop else "null")

    def ex_Attr(self, e):
        return "attr(%s, %s)" % (self.expr(e.obj), jstring(e.name))

    def ex_Call(self, e):
        f = e.func
        args = [self.expr(a) for a in e.args]
        if f.kind == "Name" and not self.is_variable(f.name):
            n = f.name
            if n in self.functions:
                d = self.functions[n]
                pnames = [p for p, _ in d.params]
                if len(args) > len(pnames):
                    raise EchoSyntaxError("%s() takes %d values but got %d." % (n, len(pnames), len(args)), e.line)
                kw = dict(e.kwargs)
                for k in kw:
                    if k not in pnames:
                        raise EchoSyntaxError("%s() has no setting called '%s'." % (n, k), e.line)
                full = list(args)
                for p, default in d.params[len(args):]:
                    if p in kw:
                        full.append(self.expr(kw[p]))
                    elif default is not None:
                        full.append(self.expr(default))
                    else:
                        raise EchoSyntaxError("%s() is missing the value for '%s'." % (n, p), e.line)
                prefix = (self.cls + ".") if self.ctx and self.ctx["lambda"] is not None else ""
                return "%s%s(%s)" % (prefix, jname(n), ", ".join(full))
            if n in self.builtins:
                if n == "ai_setup" or n not in RUNTIME_SUPPORTED:
                    raise EchoSyntaxError("Java: the built-in %s() is only available in the Echo interpreter." % n,
                                          e.line, "Supported in Java: core, bio, gates, cyber, statistics, ai().")
                kws = ["kw(%s, %s)" % (jstring(k), self.expr(v)) for k, v in e.kwargs]
                return "%s(%s)" % (RUNTIME_NAME_FIX.get(n, n), ", ".join(args + kws))
        kws = ["kw(%s, %s)" % (jstring(k), self.expr(v)) for k, v in e.kwargs]
        return "call(%s)" % ", ".join([self.expr(f)] + args + kws)

    def is_variable(self, n):
        ctx = self.ctx
        if ctx:
            lam = ctx["lambda"]
            if lam and (n in lam["params"] or n in lam["captured"]):
                return True
            if n in ctx["locals"] and n not in ctx["global_decl"]:
                return True
        return n in self.globals


RUNTIME_SUPPORTED = {
    "print", "input", "type", "length", "len", "size", "text", "str", "number", "int", "abs", "round", "floor",
    "ceil", "sqrt", "min", "max", "sum", "random", "random_int", "choose", "range", "append", "push", "pop",
    "insert", "remove", "sort", "reverse", "map", "filter", "reduce", "unique", "join", "split", "upper", "lower",
    "trim", "replace", "contains", "starts_with", "ends_with", "find", "index_of", "count", "format", "keys",
    "values", "has", "get", "now", "today", "slice",
    "dna", "gc", "gc_content", "at", "gc_count", "base_counts", "complement", "reverse_complement", "revcomp",
    "transcribe", "back_transcribe", "translate", "find_orfs", "find_motif", "hamming", "mutate", "tm", "tm_basic",
    "primer_check", "primer_info", "design_primers", "pcr_program", "enzymes", "restriction_sites", "digest",
    "align", "protein_mass", "isoelectric_point", "gravy", "protein_info", "dna_mass", "dilute", "copy_number",
    "parse_fasta", "to_fasta",
    "gate", "truth_table", "half_adder", "full_adder", "add_binary", "bit_and", "bit_or", "bit_xor", "bit_not",
    "shift_left", "shift_right", "to_binary", "from_binary", "to_hex", "from_hex", "count_ones",
    "md5", "sha1", "sha256", "sha512", "base64_encode", "base64_decode", "hex_encode", "hex_decode", "caesar",
    "rot13", "caesar_crack", "vigenere", "entropy", "password_strength", "random_password",
    "mean", "average", "median", "variance", "stdev", "sd", "correlation", "normalize", "linear_fit", "predict",
    "train", "probability", "accuracy", "cluster", "gel",
    "ai",
}


def to_java(source, class_name="Program"):
    cls = "".join(c if c.isalnum() or c == "_" else "_" for c in class_name)
    if not cls or not cls[0].isalpha():
        cls = "Echo" + cls
    cls = cls[0].upper() + cls[1:]
    return JavaGen(cls).program(parse(source))
