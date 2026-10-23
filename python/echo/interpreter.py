"""Runs Echo syntax trees."""
import difflib
import os
import sys

from .errors import EchoError, EchoRuntimeError, EchoStopped, EchoTypeError
from .parser import parse
from .values import (BASE_TYPES, Builtin, EchoFunction, Module, RecordType, describe_value, matches, show,
                     type_name)

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class Scope:
    def __init__(self, parent=None, is_function=False):
        self.vars = {}
        self.types = {}           # name -> TypeSpec for variables declared with a type
        self.parent = parent
        self.globals_declared = set()
        self.is_function = is_function

    def lookup(self, name):
        s = self
        while s is not None:
            if name in s.vars:
                return True, s.vars[name]
            s = s.parent
        return False, None

    def owner(self, name):
        s = self
        while s is not None:
            if name in s.vars:
                return s
            s = s.parent
        return None


def _bit(v):
    return isinstance(v, int) and not isinstance(v, bool) and v in (0, 1)


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def error_record(e):
    """What `catch problem` receives."""
    return {"_type": "Error", "code": e.code, "message": e.message, "line": e.line}


class Interpreter:
    def __init__(self, output=None, input_fn=None, should_stop=None, max_depth=400, base_dir=None):
        from . import stdlib
        self.output = output or (lambda text: print(text))
        self.input_fn = input_fn or (lambda prompt: input(prompt))
        self.should_stop = should_stop
        self.max_depth = max_depth
        self.depth = 0
        self.ticks = 0
        self.base_dir = base_dir or os.getcwd()
        self.builtins, self.modules = stdlib.load()
        self.globals = Scope()
        self.record_types = {}
        self.loaded_files = {}

    # ---- entry points ----
    def run(self, source, filename=None):
        tree = parse(source)
        if filename:
            self.base_dir = os.path.dirname(os.path.abspath(filename))
        self.exec_block(tree.body, self.globals)
        return self.globals

    def say(self, *values):
        self.output(" ".join(show(v) for v in values))

    # ---- helpers ----
    def tick(self):
        self.ticks += 1
        if self.should_stop and self.ticks % 200 == 0 and self.should_stop():
            raise EchoStopped()

    def error(self, message, line, hint=None, code=None):
        return EchoRuntimeError(message, line, hint, code)

    def type_error(self, message, line, hint=None, code="E301"):
        return EchoTypeError(message, line, hint, code)

    def check_type(self, value, spec, what, line):
        """Raise E302 if value doesn't fit spec. `what` names the place, e.g. "variable 'x'"."""
        if spec is None:
            return
        self.validate_type(spec, line)
        if not matches(value, spec):
            raise self.type_error("%s must be %s, but got %s." % (what, spec, describe_value(value)), line,
                                  code="E302")

    def validate_type(self, spec, line):
        while spec is not None:
            if spec.name not in BASE_TYPES and spec.name not in self.record_types:
                close = difflib.get_close_matches(spec.name, list(BASE_TYPES) + list(self.record_types), n=1)
                raise self.type_error("Unknown type '%s'." % spec.name, spec.line or line,
                                      "Did you mean '%s'?" % close[0] if close else
                                      "Types: number, integer, text, boolean, list, map, function, dna, rna, "
                                      "protein, any, or a record name.", code="E304")
            spec = spec.of

    def lookup(self, name, scope, line):
        found, value = scope.lookup(name)
        if found:
            return value
        if name in self.builtins:
            return self.builtins[name]
        if name in self.modules:
            return self.modules[name]
        from .modules import old_name_hint
        hint = old_name_hint(name)
        if not hint:
            names = set(self.builtins) | set(self.modules)
            s = scope
            while s:
                names.update(s.vars)
                s = s.parent
            close = difflib.get_close_matches(name, list(names), n=1, cutoff=0.75)
            hint = "Did you mean '%s'?" % close[0] if close else "Set it first: set %s to ..." % name
        raise self.error("Unknown name '%s'." % name, line, hint, code="E201")

    def assign_name(self, name, value, scope, line=None, declare=None):
        if name in scope.globals_declared:
            scope = self.globals
        if declare is not None:
            self.check_type(value, declare, "Variable '%s'" % name, line)
            scope.types[name] = declare
            scope.vars[name] = value
            return
        owner = scope if name in scope.vars or scope is self.globals else None
        target = owner or scope
        spec = target.types.get(name)
        if spec is not None:
            self.check_type(value, spec, "Variable '%s'" % name, line)
        target.vars[name] = value

    def condition(self, node, scope, word):
        v = self.eval(node, scope)
        if not isinstance(v, bool):
            raise self.type_error("The %s condition must be true or false, not %s." % (word, describe_value(v)),
                                  node.line, "Compare it, e.g. %s length(items) > 0%s"
                                  % (word, "" if word == "while" else " then"), code="E303")
        return v

    # ---- statements ----
    def exec_block(self, body, scope):
        for st in body:
            self.execute(st, scope)

    def execute(self, st, scope):
        method = getattr(self, "ex_" + st.kind)
        try:
            return method(st, scope)
        except (BreakSignal, ContinueSignal, ReturnSignal, EchoError, EchoStopped):
            raise
        except RecursionError:
            raise self.error("Too much recursion (a function calls itself too many times).", st.line, code="E405")
        except ZeroDivisionError:
            raise self.error("Division by zero.", st.line, code="E401")
        except KeyboardInterrupt:
            raise EchoStopped()
        except Exception as e:  # unexpected Python error inside a built-in
            raise self.error(str(e) or e.__class__.__name__, st.line, code="E404")

    def ex_ExprStmt(self, st, scope):
        self.eval(st.expr, scope)

    def ex_Say(self, st, scope):
        self.say(*[self.eval(v, scope) for v in st.values])

    def ex_Set(self, st, scope):
        value = self.eval(st.value, scope)
        self.store(st.target, value, scope, st.line, st.type)

    def store(self, target, value, scope, line, declare=None):
        if target.kind == "Name":
            self.assign_name(target.name, value, scope, line, declare)
        elif target.kind == "Index":
            obj = self.eval(target.obj, scope)
            key = self.eval(target.index, scope)
            if isinstance(obj, list):
                obj[self.list_index(obj, key, target.line)] = value
            elif isinstance(obj, dict) and "_type" not in obj:
                obj[key] = value
            else:
                raise self.type_error("Only list items and map keys can be set, not items of %s." % type_name(obj),
                                      target.line, "Text can't be changed in place; build new text with + or replace().")
        elif target.kind == "Attr":
            obj = self.eval(target.obj, scope)
            if isinstance(obj, dict) and "_type" in obj:
                rec = self.record_types.get(obj["_type"])
                if rec is not None:
                    field = next((f for f in rec.fields if f[0] == target.name), None)
                    if field is None:
                        raise self.error("Record %s has no field '%s'." % (rec.name, target.name), target.line,
                                         "Fields: " + ", ".join(f[0] for f in rec.fields), code="E202")
                    self.check_type(value, field[2], "Field %s.%s" % (rec.name, target.name), target.line)
                obj[target.name] = value
            elif isinstance(obj, dict):
                obj[target.name] = value
            else:
                raise self.type_error("Only maps and records have fields you can set, not %s." % type_name(obj),
                                      target.line)

    def ex_Add(self, st, scope):
        value = self.eval(st.value, scope)
        target = self.eval(st.target, scope)
        if not isinstance(target, list):
            raise self.type_error("'add ... to' needs a list, not %s." % type_name(target), st.line,
                                  "For numbers write: set total to total + value", code="E301")
        target.append(value)

    def ex_Ask(self, st, scope):
        prompt = self.eval(st.prompt, scope)
        answer = self.input_fn(show(prompt) + " ")
        answer = "" if answer is None else str(answer)
        text = answer.strip()
        if text and text[0] in "+-0123456789.":
            try:
                answer = float(text) if any(c in text for c in ".eE") else int(text)
            except ValueError:
                pass
        self.assign_name(st.name, answer, scope, st.line)

    def ex_If(self, st, scope):
        for i, (cond, body) in enumerate(st.branches):
            if self.condition(cond, scope, "if" if i == 0 else "else if"):
                self.exec_block(body, scope)
                return
        if st.else_body is not None:
            self.exec_block(st.else_body, scope)

    def run_loop_body(self, body, scope):
        self.tick()
        try:
            self.exec_block(body, scope)
        except ContinueSignal:
            pass

    def ex_Repeat(self, st, scope):
        count = self.eval(st.count, scope)
        if not matches(count, _INTEGER) or count < 0:
            raise self.type_error("repeat needs a whole number of times, not %s." % describe_value(count), st.line)
        try:
            for _ in range(int(count)):
                self.run_loop_body(st.body, scope)
        except BreakSignal:
            pass

    def ex_While(self, st, scope):
        try:
            while self.condition(st.cond, scope, "while"):
                self.run_loop_body(st.body, scope)
        except BreakSignal:
            pass

    def ex_ForEach(self, st, scope):
        it = self.eval(st.iterable, scope)
        if isinstance(it, dict):
            items = [(k, v) for k, v in it.items() if k != "_type"] if st.var2 else [k for k in it if k != "_type"]
        elif isinstance(it, (list, str, tuple)):
            items = list(enumerate(it)) if st.var2 else list(it)
        else:
            raise self.type_error("Can't loop over %s." % type_name(it), st.line,
                                  "Loop over a list, text or map. For numbers write: for i from 1 to n")
        try:
            for item in items:
                if st.var2:
                    self.assign_name(st.var, item[0], scope, st.line)
                    self.assign_name(st.var2, item[1], scope, st.line)
                else:
                    self.assign_name(st.var, item, scope, st.line)
                self.run_loop_body(st.body, scope)
        except BreakSignal:
            pass

    def ex_ForRange(self, st, scope):
        start = self.eval(st.start, scope)
        stop = self.eval(st.stop, scope)
        for v, what in ((start, "start"), (stop, "end")):
            if not _isnum(v):
                raise self.type_error("The loop %s must be a number, not %s." % (what, describe_value(v)), st.line)
        step = self.eval(st.step, scope) if st.step is not None else (1 if stop >= start else -1)
        if not _isnum(step):
            raise self.type_error("The loop step must be a number.", st.line)
        if step == 0:
            raise self.error("The loop step can't be 0.", st.line, code="E404")
        i = start
        try:
            while (i <= stop) if step > 0 else (i >= stop):
                self.assign_name(st.var, i, scope, st.line)
                self.run_loop_body(st.body, scope)
                i = i + step
        except BreakSignal:
            pass

    def ex_Break(self, st, scope):
        raise BreakSignal()

    def ex_Continue(self, st, scope):
        raise ContinueSignal()

    def ex_Define(self, st, scope):
        self.assign_name(st.name, EchoFunction(st.name, st.params, st.body, scope, returns=st.returns), scope, st.line)

    def ex_Return(self, st, scope):
        raise ReturnSignal(self.eval(st.value, scope) if st.value is not None else None)

    def ex_Try(self, st, scope):
        try:
            self.exec_block(st.body, scope)
        except EchoError as e:
            if st.err:
                self.assign_name(st.err, error_record(e), scope, st.line)
            self.exec_block(st.handler, scope)

    def ex_Fail(self, st, scope):
        raise self.error(show(self.eval(st.value, scope)), st.line, code="E407")

    def ex_Global(self, st, scope):
        scope.globals_declared.update(st.names)

    def ex_Record(self, st, scope):
        name, fields = st.name, st.fields
        interp = self

        def make(*args, **kwargs):
            if len(args) > len(fields):
                raise EchoRuntimeError("%s() takes %d value%s but got %d." % (
                    name, len(fields), "" if len(fields) == 1 else "s", len(args)), code="E203")
            obj = {"_type": name}
            for i, (fname, default, ftype) in enumerate(fields):
                if i < len(args):
                    value = args[i]
                elif fname in kwargs:
                    value = kwargs.pop(fname)
                elif default is not None:
                    value = interp.eval(default, scope)
                else:
                    raise EchoRuntimeError("%s() is missing the value for '%s'." % (name, fname), code="E205")
                interp.check_type(value, ftype, "Field %s.%s" % (name, fname), None)
                obj[fname] = value
            if kwargs:
                raise EchoRuntimeError("%s has no field '%s'." % (name, next(iter(kwargs))),
                                       hint="Fields: " + ", ".join(f[0] for f in fields), code="E204")
            return obj

        rec = RecordType(name, fields, make)
        self.record_types[name] = rec
        self.assign_name(name, rec, scope, st.line)

    def ex_Use(self, st, scope):
        path = st.path if st.path.endswith(".echo") else st.path + ".echo"
        full = path if os.path.isabs(path) else os.path.join(self.base_dir, path)
        full = os.path.normpath(full)
        name = st.alias or os.path.splitext(os.path.basename(path))[0]
        if not name.isidentifier():
            raise self.error("'%s' is not a usable module name." % name, st.line,
                             'Give it one: use "%s" as helpers' % st.path, code="E101")
        if full not in self.loaded_files:
            if not os.path.exists(full):
                raise self.error("Can't find the file '%s'." % path, st.line,
                                 "Paths are relative to the program's own folder.", code="E501")
            with open(full, encoding="utf-8") as f:
                source = f.read()
            self.loaded_files[full] = None  # guards against a file using itself
            module_scope = Scope()
            old = self.base_dir
            self.base_dir = os.path.dirname(full)
            try:
                self.exec_block(parse(source).body, module_scope)
            finally:
                self.base_dir = old
            members = {k: v for k, v in module_scope.vars.items() if not k.startswith("_")}
            self.loaded_files[full] = Module(name, members, "functions from " + path)
        module = self.loaded_files[full]
        if module is None:
            raise self.error("'%s' uses itself." % path, st.line, code="E501")
        self.assign_name(name, module, scope, st.line)

    # ---- expressions ----
    def eval(self, node, scope):
        return getattr(self, "ev_" + node.kind)(node, scope)

    def ev_Num(self, n, scope):
        return n.value

    def ev_Bool(self, n, scope):
        return n.value

    def ev_Nothing(self, n, scope):
        return None

    def ev_Str(self, n, scope):
        return "".join(p if isinstance(p, str) else show(self.eval(p, scope)) for p in n.parts)

    def ev_List(self, n, scope):
        return [self.eval(x, scope) for x in n.items]

    def ev_Map(self, n, scope):
        return {self.eval(k, scope): self.eval(v, scope) for k, v in n.pairs}

    def ev_Name(self, n, scope):
        return self.lookup(n.name, scope, n.line)

    def ev_Lambda(self, n, scope):
        return EchoFunction("fn", n.params, n.body, scope, is_lambda=True)

    def ev_Neg(self, n, scope):
        v = self.eval(n.expr, scope)
        if not _isnum(v):
            raise self.type_error("Can't make %s negative." % type_name(v), n.line)
        return -v

    def ev_Not(self, n, scope):
        v = self.eval(n.expr, scope)
        if isinstance(v, bool):
            return not v
        if _bit(v):
            return 1 - v
        raise self.type_error("'not' needs true/false or a bit (0 or 1), not %s." % describe_value(v), n.line)

    def ev_Logic(self, n, scope):
        op = n.op
        a = self.eval(n.left, scope)
        if not isinstance(a, bool) and not _bit(a):
            raise self.type_error("'%s' needs true/false or bits (0 or 1), not %s." % (op, describe_value(a)), n.line)
        if op == "and" and not a:
            return a
        if op == "or" and a and isinstance(a, bool):
            return True
        if op == "or" and a == 1 and not isinstance(a, bool):
            return 1
        b = self.eval(n.right, scope)
        if isinstance(a, bool) != isinstance(b, bool) or (not isinstance(b, bool) and not _bit(b)):
            raise self.type_error("'%s' needs both sides to be true/false, or both to be bits (0 or 1); got %s and %s."
                                  % (op, describe_value(a), describe_value(b)), n.line)
        x, y = bool(a), bool(b)
        result = {
            "and": x and y, "or": x or y, "xor": x != y, "nand": not (x and y),
            "nor": not (x or y), "xnor": x == y,
        }[op]
        return result if isinstance(a, bool) else (1 if result else 0)

    def ev_Compare(self, n, scope):
        a = self.eval(n.left, scope)
        b = self.eval(n.right, scope)
        op = n.op
        if op == "==":
            return a == b and (isinstance(a, bool) == isinstance(b, bool))
        if op == "!=":
            return not (a == b and (isinstance(a, bool) == isinstance(b, bool)))
        if op in ("in", "not in"):
            if isinstance(b, str):
                if not isinstance(a, str):
                    raise self.type_error("To look inside text, the left side must be text, not %s." % type_name(a),
                                          n.line)
                r = a in b
            elif isinstance(b, list):
                r = a in b
            elif isinstance(b, dict):
                r = a in b and a != "_type"
            else:
                raise self.type_error("Can't look inside %s." % type_name(b), n.line)
            return r if op == "in" else not r
        if not ((_isnum(a) and _isnum(b)) or (isinstance(a, str) and isinstance(b, str))):
            raise self.type_error("Can't compare %s with %s using %s." % (type_name(a), type_name(b), op), n.line)
        return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]

    def ev_BinOp(self, n, scope):
        return self.binop(n.op, self.eval(n.left, scope), self.eval(n.right, scope), n.line)

    def binop(self, op, a, b, line):
        if op == "+":
            if _isnum(a) and _isnum(b):
                return a + b
            if isinstance(a, str) or isinstance(b, str):
                return show(a) + show(b)
            if isinstance(a, list) and isinstance(b, list):
                return a + b
            if isinstance(a, dict) and isinstance(b, dict) and "_type" not in a and "_type" not in b:
                c = dict(a)
                c.update(b)
                return c
            raise self.type_error("Can't add %s and %s." % (type_name(a), type_name(b)), line)
        if op == "*":
            if _isnum(a) and _isnum(b):
                return a * b
            if isinstance(a, (str, list)) and isinstance(b, int) and not isinstance(b, bool):
                return a * b
            if isinstance(b, (str, list)) and isinstance(a, int) and not isinstance(a, bool):
                return b * a
            raise self.type_error("Can't multiply %s by %s." % (type_name(a), type_name(b)), line)
        if not (_isnum(a) and _isnum(b)):
            raise self.type_error("'%s' needs two numbers, not %s and %s." % (op, type_name(a), type_name(b)), line)
        if op == "-":
            return a - b
        if op in ("/", "//", "%") and b == 0:
            raise self.error("Division by zero.", line, code="E401")
        if op == "/":
            if isinstance(a, int) and isinstance(b, int) and a % b == 0:
                return a // b
            return a / b
        if op == "//":
            return a // b
        if op == "%":
            return a % b
        if op == "^":
            return a ** b
        raise self.error("Unknown operator %s." % op, line)

    def list_index(self, obj, key, line):
        if not matches(key, _INTEGER):
            raise self.type_error("A position must be a whole number, not %s." % describe_value(key), line)
        key = int(key)
        n = len(obj)
        if key < -n or key >= n:
            raise self.error("Position %d is outside (it has %d item%s; positions start at 0)."
                             % (key, n, "" if n == 1 else "s"), line, code="E402")
        return key

    def ev_Index(self, n, scope):
        obj = self.eval(n.obj, scope)
        key = self.eval(n.index, scope)
        if isinstance(obj, (list, str, tuple)):
            return obj[self.list_index(obj, key, n.line)]
        if isinstance(obj, dict):
            if key not in obj or key == "_type":
                keys = ", ".join(show(k) for k in list(obj)[:8] if k != "_type")
                raise self.error("The map has no key %s." % show(key, True), n.line,
                                 "Keys are: %s. Use get(map, key, default) for keys that may be missing." % keys,
                                 code="E403")
            return obj[key]
        raise self.type_error("Can't take an item from %s." % type_name(obj), n.line)

    def ev_Slice(self, n, scope):
        obj = self.eval(n.obj, scope)
        a = self.eval(n.start, scope) if n.start is not None else None
        b = self.eval(n.stop, scope) if n.stop is not None else None
        if not isinstance(obj, (list, str)):
            raise self.type_error("Only text and lists can be sliced, not %s." % type_name(obj), n.line)
        for v in (a, b):
            if v is not None and not matches(v, _INTEGER):
                raise self.type_error("Slice positions must be whole numbers, not %s." % describe_value(v), n.line)
        return obj[None if a is None else int(a):None if b is None else int(b)]

    def ev_Attr(self, n, scope):
        obj = self.eval(n.obj, scope)
        if isinstance(obj, Module):
            if n.name in obj.members:
                return obj.members[n.name]
            close = difflib.get_close_matches(n.name, list(obj.members), n=1, cutoff=0.6)
            hint = "Did you mean %s.%s?" % (obj.name, close[0]) if close else 'See help("%s").' % obj.name
            raise self.error("Module %s has no '%s'." % (obj.name, n.name), n.line, hint, code="E202")
        if isinstance(obj, dict):
            if n.name in obj and n.name != "_type":
                return obj[n.name]
            fields = [k for k in obj if k != "_type"]
            close = difflib.get_close_matches(n.name, [str(f) for f in fields], n=1, cutoff=0.6)
            hint = "Did you mean '%s'?" % close[0] if close else "Fields: " + ", ".join(str(f) for f in fields[:10])
            raise self.error("%s has no field '%s'." % ("This map" if "_type" not in obj else obj["_type"], n.name),
                             n.line, hint, code="E202")
        from .modules import QUALNAME
        hint = None
        for internal, qual in QUALNAME.items():
            if qual.endswith("." + n.name) or qual == n.name:
                hint = "Echo 2 has no method calls on values. Write: %s(value)" % qual
                break
        raise self.error("%s has no field '%s'." % (type_name(obj).capitalize(), n.name), n.line, hint, code="E202")

    def ev_Call(self, n, scope):
        f = self.eval(n.func, scope)
        args = [self.eval(a, scope) for a in n.args]
        kwargs = {k: self.eval(v, scope) for k, v in n.kwargs}
        return self.call_value(f, args, kwargs, n.line)

    def call_value(self, f, args, kwargs=None, line=None):
        kwargs = kwargs or {}
        if isinstance(f, Builtin):
            try:
                if f.needs_interp:
                    return f.fn(self, *args, **kwargs)
                return f.fn(*args, **kwargs)
            except EchoError as e:
                if e.line is None:
                    e.line = line
                raise
            except TypeError as e:
                msg = str(e)
                if "unexpected keyword" in msg:
                    bad = msg.split("'")[-2] if "'" in msg else "?"
                    raise self.error("%s() has no setting called '%s'." % (f.qualname, bad), line,
                                     f.doc or None, code="E204")
                if "argument" in msg:
                    raise self.error("Wrong number of values for %s()." % f.qualname, line,
                                     f.doc or "Check how many values it needs.", code="E203")
                raise self.type_error("%s(): %s" % (f.qualname, msg), line)
            except ZeroDivisionError:
                raise self.error("%s(): division by zero." % f.qualname, line, code="E401")
            except (ValueError, IndexError, KeyError) as e:
                raise self.error("%s(): %s" % (f.qualname, e), line, f.doc or None, code="E404")
            except OSError as e:
                raise self.error("%s(): %s" % (f.qualname, e.strerror or e), line, code="E501")
        if isinstance(f, EchoFunction):
            return self.call_function(f, args, kwargs, line)
        if isinstance(f, RecordType):
            try:
                return f.make(*args, **kwargs)
            except EchoError as e:
                if e.line is None:
                    e.line = line
                raise
        if isinstance(f, Module):
            raise self.type_error("%s is a module, not a function." % f.name, line,
                                  'Call one of its functions, e.g. %s.something(...). See help("%s").'
                                  % (f.name, f.name), code="E206")
        if callable(f):  # a plain Python function (used by converted Python code)
            return f(*args, **kwargs)
        raise self.type_error("%s is not a function, so it can't be called." % describe_value(f), line, code="E206")

    def call_function(self, f, args, kwargs, line):
        if len(args) > len(f.params):
            raise self.error("%s() takes %d value%s but got %d." % (
                f.name, len(f.params), "" if len(f.params) == 1 else "s", len(args)), line, code="E203")
        unknown = [k for k in kwargs if k not in {p[0] for p in f.params}]
        if unknown:
            raise self.error("%s() has no setting called '%s'." % (f.name, unknown[0]), line,
                             "Its parameters: " + ", ".join(p[0] for p in f.params), code="E204")
        local = Scope(f.closure, is_function=True)
        for i, (pname, default, ptype) in enumerate(f.params):
            if i < len(args):
                value = args[i]
            elif pname in kwargs:
                value = kwargs.pop(pname)
            elif default is not None:
                value = self.eval(default, local)
            else:
                raise self.error("%s() is missing the value for '%s'." % (f.name, pname), line, code="E205")
            self.check_type(value, ptype, "Parameter '%s' of %s()" % (pname, f.name), line)
            local.vars[pname] = value
            if ptype is not None:
                local.types[pname] = ptype
        if kwargs:
            raise self.error("%s() has no setting called '%s'." % (f.name, next(iter(kwargs))), line,
                             "Its parameters: " + ", ".join(p[0] for p in f.params), code="E204")
        self.depth += 1
        if self.depth > self.max_depth:
            self.depth = 0
            raise self.error("Too much recursion: %s() called itself more than %d times." % (f.name, self.max_depth),
                             line, code="E405")
        self.tick()
        try:
            if f.is_lambda:
                result = self.eval(f.body, local)
            else:
                self.exec_block(f.body, local)
                result = None
        except ReturnSignal as r:
            result = r.value
        finally:
            self.depth -= 1
        if f.returns is not None:
            self.check_type(result, f.returns, "The result of %s()" % f.name, line)
        return result


class _Spec:
    def __init__(self, name):
        self.name, self.of, self.optional, self.line = name, None, False, None


_INTEGER = _Spec("integer")


def run_source(source, output=None, input_fn=None, should_stop=None, filename=None):
    """Run Echo code. Returns (ok, error_text)."""
    interp = Interpreter(output=output, input_fn=input_fn, should_stop=should_stop)
    try:
        interp.run(source, filename)
        return True, None
    except EchoStopped:
        return False, "Error E406: Stopped."
    except EchoError as e:
        return False, str(e)
