"""Runs Echo syntax trees."""
import difflib
import os
import sys

from .errors import EchoError, EchoRuntimeError, EchoStopped
from .parser import parse
from .values import Builtin, BoundBuiltin, EchoFunction, show, truthy, type_name

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


def _bit(v):
    return isinstance(v, int) and not isinstance(v, bool) and v in (0, 1)


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
        self.builtins = stdlib.load()
        self.globals = Scope()
        self.used = set()

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
    def tick(self, line):
        self.ticks += 1
        if self.should_stop and self.ticks % 200 == 0 and self.should_stop():
            raise EchoStopped()

    def error(self, message, line, hint=None):
        return EchoRuntimeError(message, line, hint)

    def lookup(self, name, scope, line):
        found, value = scope.lookup(name)
        if found:
            return value
        if name in self.builtins:
            return self.builtins[name]
        names = set(self.builtins)
        s = scope
        while s:
            names.update(s.vars)
            s = s.parent
        close = difflib.get_close_matches(name, list(names), n=1, cutoff=0.75)
        hint = "Did you mean '%s'?" % close[0] if close else "Set it first: set %s to ..." % name
        raise self.error("I don't know '%s'." % name, line, hint)

    def assign_name(self, name, value, scope):
        if name in scope.globals_declared:
            self.globals.vars[name] = value
        else:
            scope.vars[name] = value

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
            raise self.error("Too much recursion (a function calls itself too many times).", st.line)
        except ZeroDivisionError:
            raise self.error("Can't divide by zero.", st.line)
        except KeyboardInterrupt:
            raise EchoStopped()
        except Exception as e:  # unexpected Python error inside a built-in
            raise self.error(str(e) or e.__class__.__name__, st.line)

    def ex_ExprStmt(self, st, scope):
        self.eval(st.expr, scope)

    def ex_Pass(self, st, scope):
        pass

    def ex_Say(self, st, scope):
        self.say(*[self.eval(v, scope) for v in st.values])

    def ex_Set(self, st, scope):
        value = self.eval(st.value, scope)
        if st.op != "=":
            current = self.eval(st.target, scope)
            value = self.binop(st.op[0], current, value, st.line)
        self.store(st.target, value, scope)

    def store(self, target, value, scope):
        if target.kind == "Name":
            if target.name in self.builtins and not scope.lookup(target.name)[0]:
                pass  # shadowing a built-in is allowed
            self.assign_name(target.name, value, scope)
        elif target.kind == "Index":
            obj = self.eval(target.obj, scope)
            key = self.eval(target.index, scope)
            if isinstance(obj, list):
                idx = self.list_index(obj, key, target.line)
                obj[idx] = value
            elif isinstance(obj, dict):
                obj[key] = value
            else:
                raise self.error("You can only change items of a list or map, not %s." % type_name(obj), target.line,
                                 "Text can't be changed in place; build new text with + or replace().")
        elif target.kind == "Attr":
            obj = self.eval(target.obj, scope)
            if not isinstance(obj, dict):
                raise self.error("Only maps and records have fields you can set.", target.line)
            obj[target.name] = value

    def ex_Add(self, st, scope):
        value = self.eval(st.value, scope)
        target = self.eval(st.target, scope)
        if isinstance(target, list):
            target.append(value)
        elif isinstance(target, (int, float)) and isinstance(value, (int, float)):
            self.store(st.target, target + value, scope)
        elif isinstance(target, str):
            self.store(st.target, target + show(value), scope)
        else:
            raise self.error("Can't add to %s." % type_name(target), st.line)

    def ex_Ask(self, st, scope):
        prompt = self.eval(st.prompt, scope)
        if st.ai:
            answer = self.builtins["ai"].fn(show(prompt))
            if st.name:
                self.assign_name(st.name, answer, scope)
            else:
                self.output(answer)
            return
        answer = self.input_fn(show(prompt) + " ")
        if answer is None:
            answer = ""
        answer = str(answer)
        try:
            num = float(answer) if any(c in answer for c in ".eE") else int(answer)
            if answer.strip() and answer.strip()[0] in "+-0123456789.":
                answer = num
        except ValueError:
            pass
        self.assign_name(st.name, answer, scope)

    def ex_If(self, st, scope):
        for cond, body in st.branches:
            if truthy(self.eval(cond, scope)):
                self.exec_block(body, scope)
                return
        if st.else_body is not None:
            self.exec_block(st.else_body, scope)

    def run_loop_body(self, body, scope, line):
        self.tick(line)
        try:
            self.exec_block(body, scope)
        except ContinueSignal:
            pass

    def ex_Repeat(self, st, scope):
        count = self.eval(st.count, scope)
        if not isinstance(count, (int, float)) or isinstance(count, bool):
            raise self.error("repeat needs a number of times, not %s." % type_name(count), st.line)
        try:
            for _ in range(int(count)):
                self.run_loop_body(st.body, scope, st.line)
        except BreakSignal:
            pass

    def ex_While(self, st, scope):
        try:
            while truthy(self.eval(st.cond, scope)):
                self.run_loop_body(st.body, scope, st.line)
        except BreakSignal:
            pass

    def ex_ForEach(self, st, scope):
        it = self.eval(st.iterable, scope)
        if isinstance(it, dict):
            items = [(k, v) for k, v in it.items() if k != "_type"] if st.var2 else [k for k in it if k != "_type"]
        elif isinstance(it, (list, str, tuple)):
            items = list(enumerate(it)) if st.var2 else list(it)
        elif isinstance(it, (int, float)) and not isinstance(it, bool):
            items = list(range(int(it)))
        else:
            raise self.error("Can't loop over %s." % type_name(it), st.line)
        try:
            for item in items:
                if st.var2:
                    self.assign_name(st.var, item[0], scope)
                    self.assign_name(st.var2, item[1], scope)
                else:
                    self.assign_name(st.var, item, scope)
                self.run_loop_body(st.body, scope, st.line)
        except BreakSignal:
            pass

    def ex_ForRange(self, st, scope):
        start = self.eval(st.start, scope)
        stop = self.eval(st.stop, scope)
        step = self.eval(st.step, scope) if st.step is not None else (1 if stop >= start else -1)
        for v, what in ((start, "start"), (stop, "end"), (step, "step")):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise self.error("The loop %s must be a number." % what, st.line)
        if step == 0:
            raise self.error("step can't be 0.", st.line)
        i = start
        try:
            while (i <= stop) if step > 0 else (i >= stop):
                self.assign_name(st.var, i, scope)
                self.run_loop_body(st.body, scope, st.line)
                i = i + step
        except BreakSignal:
            pass

    def ex_Break(self, st, scope):
        raise BreakSignal()

    def ex_Continue(self, st, scope):
        raise ContinueSignal()

    def ex_Define(self, st, scope):
        self.assign_name(st.name, EchoFunction(st.name, st.params, st.body, scope), scope)

    def ex_Return(self, st, scope):
        raise ReturnSignal(self.eval(st.value, scope) if st.value is not None else None)

    def ex_Try(self, st, scope):
        try:
            self.exec_block(st.body, scope)
        except EchoError as e:
            if st.err:
                self.assign_name(st.err, e.message, scope)
            self.exec_block(st.handler, scope)

    def ex_Fail(self, st, scope):
        raise self.error(show(self.eval(st.value, scope)), st.line)

    def ex_Global(self, st, scope):
        scope.globals_declared.update(st.names)

    def ex_Record(self, st, scope):
        name, fields = st.name, st.fields
        interp = self

        def make(*args, **kwargs):
            if len(args) > len(fields):
                raise EchoRuntimeError("%s takes %d values but got %d." % (name, len(fields), len(args)))
            obj = {"_type": name}
            for i, (fname, default) in enumerate(fields):
                if i < len(args):
                    obj[fname] = args[i]
                elif fname in kwargs:
                    obj[fname] = kwargs.pop(fname)
                elif default is not None:
                    obj[fname] = interp.eval(default, scope)
                else:
                    obj[fname] = None
            if kwargs:
                raise EchoRuntimeError("%s has no field '%s'." % (name, next(iter(kwargs))))
            return obj

        self.assign_name(name, Builtin(name, make), scope)

    def ex_Use(self, st, scope):
        path = st.path
        if not path.endswith(".echo"):
            if path in ("bio", "gates", "cyber", "ml", "ai", "math", "core"):
                return  # built-in libraries are always available
            path += ".echo"
        full = path if os.path.isabs(path) else os.path.join(self.base_dir, path)
        if full in self.used:
            return
        if not os.path.exists(full):
            raise self.error("Can't find the file '%s'." % path, st.line)
        self.used.add(full)
        with open(full, encoding="utf-8") as f:
            source = f.read()
        old = self.base_dir
        self.base_dir = os.path.dirname(full)
        try:
            self.exec_block(parse(source).body, self.globals)
        finally:
            self.base_dir = old

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
        out = []
        for p in n.parts:
            out.append(p if isinstance(p, str) else show(self.eval(p, scope)))
        return "".join(out)

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
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise self.error("Can't make %s negative." % type_name(v), n.line)
        return -v

    def ev_Not(self, n, scope):
        v = self.eval(n.expr, scope)
        if _bit(v):
            return 1 - v
        return not truthy(v)

    def ev_Logic(self, n, scope):
        op = n.op
        a = self.eval(n.left, scope)
        if op == "and" and not truthy(a):
            return 0 if _bit(a) else False
        if op == "or" and truthy(a):
            return 1 if _bit(a) else True
        b = self.eval(n.right, scope)
        x, y = truthy(a), truthy(b)
        result = {
            "and": x and y, "or": x or y, "xor": x != y, "nand": not (x and y),
            "nor": not (x or y), "xnor": x == y,
        }[op]
        if _bit(a) and _bit(b):
            return 1 if result else 0
        return result

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
                    raise self.error("To look inside text, the left side must be text.", n.line)
                r = a.upper() in b.upper() if _is_seq(a) and _is_seq(b) else a in b
            elif isinstance(b, (list, dict)):
                r = a in b
            else:
                raise self.error("Can't look inside %s." % type_name(b), n.line)
            return r if op == "in" else not r
        num = (int, float)
        if not ((isinstance(a, num) and isinstance(b, num)) or (isinstance(a, str) and isinstance(b, str))):
            raise self.error("Can't compare %s with %s." % (type_name(a), type_name(b)), n.line)
        return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]

    def ev_BinOp(self, n, scope):
        return self.binop(n.op, self.eval(n.left, scope), self.eval(n.right, scope), n.line)

    def binop(self, op, a, b, line):
        num = (int, float)
        isnum = lambda v: isinstance(v, num) and not isinstance(v, bool)
        if op == "+":
            if isnum(a) and isnum(b):
                return a + b
            if isinstance(a, str) or isinstance(b, str):
                return show(a) + show(b)
            if isinstance(a, list) and isinstance(b, list):
                return a + b
            if isinstance(a, dict) and isinstance(b, dict):
                c = dict(a)
                c.update(b)
                return c
            raise self.error("Can't add %s and %s." % (type_name(a), type_name(b)), line)
        if op == "*":
            if isnum(a) and isnum(b):
                return a * b
            if isinstance(a, (str, list)) and isinstance(b, int) and not isinstance(b, bool):
                return a * b
            if isinstance(b, (str, list)) and isinstance(a, int) and not isinstance(a, bool):
                return b * a
            raise self.error("Can't multiply %s by %s." % (type_name(a), type_name(b)), line)
        if not (isnum(a) and isnum(b)):
            raise self.error("'%s' needs two numbers, not %s and %s." % (op, type_name(a), type_name(b)), line)
        if op == "-":
            return a - b
        if op == "/":
            if b == 0:
                raise self.error("Can't divide by zero.", line)
            if isinstance(a, int) and isinstance(b, int) and a % b == 0:
                return a // b
            return a / b
        if op == "//":
            if b == 0:
                raise self.error("Can't divide by zero.", line)
            return a // b
        if op == "%":
            if b == 0:
                raise self.error("Can't divide by zero.", line)
            return a % b
        if op == "^":
            return a ** b
        raise self.error("Unknown operator %s." % op, line)

    def list_index(self, obj, key, line):
        if not isinstance(key, int) or isinstance(key, bool):
            if isinstance(key, float) and key == int(key):
                key = int(key)
            else:
                raise self.error("A position must be a whole number, not %s." % show(key, True), line)
        n = len(obj)
        if key < -n or key >= n:
            raise self.error("Position %d is outside (it has %d item%s; positions start at 0)."
                             % (key, n, "" if n == 1 else "s"), line)
        return key

    def ev_Index(self, n, scope):
        obj = self.eval(n.obj, scope)
        key = self.eval(n.index, scope)
        if isinstance(obj, (list, str, tuple)):
            return obj[self.list_index(obj, key, n.line)]
        if isinstance(obj, dict):
            if key not in obj:
                keys = ", ".join(show(k) for k in list(obj)[:8] if k != "_type")
                raise self.error("The map has no key %s." % show(key, True), n.line, "Keys are: " + keys)
            return obj[key]
        raise self.error("Can't take an item from %s." % type_name(obj), n.line)

    def ev_Slice(self, n, scope):
        obj = self.eval(n.obj, scope)
        a = self.eval(n.start, scope) if n.start is not None else None
        b = self.eval(n.stop, scope) if n.stop is not None else None
        if not isinstance(obj, (list, str)):
            raise self.error("Can only slice text or lists.", n.line)
        return obj[a:b]

    def ev_Attr(self, n, scope):
        obj = self.eval(n.obj, scope)
        if isinstance(obj, dict) and n.name in obj:
            return obj[n.name]
        if n.name in self.builtins:
            return BoundBuiltin(self.builtins[n.name], obj)
        if isinstance(obj, dict):
            raise self.error("No field '%s'." % n.name, n.line)
        raise self.error("%s has no '%s'." % (type_name(obj), n.name), n.line)

    def ev_Call(self, n, scope):
        f = self.eval(n.func, scope)
        args = [self.eval(a, scope) for a in n.args]
        kwargs = {k: self.eval(v, scope) for k, v in n.kwargs}
        return self.call_value(f, args, kwargs, n.line)

    def call_value(self, f, args, kwargs=None, line=None):
        kwargs = kwargs or {}
        if isinstance(f, BoundBuiltin):
            return self.call_value(f.builtin, [f.first] + list(args), kwargs, line)
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
                if "argument" in msg:
                    raise self.error("Wrong number of values for %s()." % f.name, line,
                                     f.doc or "Check how many values it needs.")
                raise self.error(msg, line)
            except (ValueError, IndexError, KeyError) as e:
                raise self.error("%s(): %s" % (f.name, e), line)
        if isinstance(f, EchoFunction):
            return self.call_function(f, args, kwargs, line)
        if callable(f):  # a plain Python function (used by converted Python code)
            return f(*args, **kwargs)
        raise self.error("%s is not a function, so it can't be called." % show(f, True), line)

    def call_function(self, f, args, kwargs, line):
        if len(args) > len(f.params):
            raise self.error("%s() takes %d value%s but got %d." % (
                f.name, len(f.params), "" if len(f.params) == 1 else "s", len(args)), line)
        local = Scope(f.closure, is_function=True)
        for i, (pname, default) in enumerate(f.params):
            if i < len(args):
                local.vars[pname] = args[i]
            elif pname in kwargs:
                local.vars[pname] = kwargs.pop(pname)
            elif default is not None:
                local.vars[pname] = self.eval(default, local)
            else:
                raise self.error("%s() is missing the value for '%s'." % (f.name, pname), line)
        if kwargs:
            raise self.error("%s() has no setting called '%s'." % (f.name, next(iter(kwargs))), line)
        self.depth += 1
        if self.depth > self.max_depth:
            self.depth = 0
            raise self.error("Too much recursion: %s() called itself more than %d times." % (f.name, self.max_depth),
                             line)
        self.tick(line)
        try:
            if f.is_lambda:
                return self.eval(f.body, local)
            self.exec_block(f.body, local)
            return None
        except ReturnSignal as r:
            return r.value
        except BreakSignal:
            raise self.error("'break' used outside a loop.", line)
        finally:
            self.depth -= 1


def _is_seq(s):
    return isinstance(s, str) and s != "" and all(c in "ACGTUNacgtun" for c in s)


def run_source(source, output=None, input_fn=None, should_stop=None, filename=None):
    """Run Echo code. Returns (ok, error_text)."""
    interp = Interpreter(output=output, input_fn=input_fn, should_stop=should_stop)
    try:
        interp.run(source, filename)
        return True, None
    except EchoStopped:
        return False, "Stopped."
    except BreakSignal:
        return False, "'break' used outside a loop."
    except ContinueSignal:
        return False, "'continue' used outside a loop."
    except ReturnSignal:
        return False, "'return' used outside a function."
    except EchoError as e:
        return False, str(e)
