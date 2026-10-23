"""Core functions: numbers, text, lists, maps, files, time."""
import json
import math
import os
import random as _random
import time

from ..errors import EchoRuntimeError
from ..values import show, type_name, truthy
from . import builtin, constant

C = "core"


def _num(v, fname):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise EchoRuntimeError("%s() needs a number, not %s." % (fname, type_name(v)))
    return v


def _list(v, fname):
    if not isinstance(v, (list, tuple, str)):
        raise EchoRuntimeError("%s() needs a list, not %s." % (fname, type_name(v)))
    return v


# ---- general ----
@builtin("type", C, "type(x) -> number, text, boolean, list, map, nothing, function, or a record name")
def _type(v):
    return type_name(v)


@builtin("length", C, "length(x) counts letters, items or keys", aliases=("len", "size"))
def _length(v):
    if isinstance(v, dict):
        return len([k for k in v if k != "_type"])
    if isinstance(v, (str, list, tuple)):
        return len(v)
    raise EchoRuntimeError("length() needs text, a list or a map, not %s." % type_name(v))


@builtin("text", C, "text(x) turns any value into text", aliases=("str",))
def _text(v):
    return show(v)


@builtin("number", C, "number(x) turns text into a number", aliases=("num",))
def _number(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            raise EchoRuntimeError("'%s' is not a number." % s)


@builtin("int", C, "int(x) whole number (cuts the decimals)")
def _int(v):
    return int(_number(v))


@builtin("bool", C, "bool(x) true or false")
def _bool(v):
    return truthy(v)


# ---- math ----
@builtin("abs", C, "abs(x)")
def _abs(x):
    return abs(_num(x, "abs"))


@builtin("round", C, "round(x, places=0)")
def _round(x, places=0):
    r = round(_num(x, "round"), int(places))
    return int(r) if places == 0 else r


@builtin("floor", C, "floor(x)")
def _floor(x):
    return math.floor(_num(x, "floor"))


@builtin("ceil", C, "ceil(x)")
def _ceil(x):
    return math.ceil(_num(x, "ceil"))


@builtin("sqrt", C, "sqrt(x)")
def _sqrt(x):
    x = _num(x, "sqrt")
    if x < 0:
        raise EchoRuntimeError("sqrt() of a negative number.")
    r = math.sqrt(x)
    return int(r) if r == int(r) else r


for _n in ("sin", "cos", "tan", "exp"):
    builtin(_n, C, "%s(x)" % _n)((lambda f: lambda x: f(_num(x, f.__name__)))(getattr(math, _n)))


@builtin("log", C, "log(x, base=e)")
def _log(x, base=None):
    x = _num(x, "log")
    if x <= 0:
        raise EchoRuntimeError("log() needs a number above 0.")
    return math.log(x) if base is None else math.log(x, base)


@builtin("log10", C, "log10(x)")
def _log10(x):
    return math.log10(_num(x, "log10"))


constant("pi", C, math.pi, "pi = 3.14159...")
constant("e", C, math.e, "e = 2.71828...")


@builtin("min", C, "min(list) or min(a, b, ...)")
def _min(*args):
    items = args[0] if len(args) == 1 and isinstance(args[0], list) else args
    if not items:
        raise EchoRuntimeError("min() of an empty list.")
    return min(items)


@builtin("max", C, "max(list) or max(a, b, ...)")
def _max(*args):
    items = args[0] if len(args) == 1 and isinstance(args[0], list) else args
    if not items:
        raise EchoRuntimeError("max() of an empty list.")
    return max(items)


@builtin("sum", C, "sum(list)")
def _sum(items):
    return sum(_list(items, "sum"))


@builtin("random", C, "random() number from 0 to 1")
def _random_():
    return _random.random()


@builtin("random_int", C, "random_int(a, b) whole number from a to b")
def _random_int(a, b):
    return _random.randint(int(a), int(b))


@builtin("choose", C, "choose(list) random item")
def _choose(items):
    if not items:
        raise EchoRuntimeError("choose() of an empty list.")
    return _random.choice(list(items))


@builtin("shuffle", C, "shuffle(list) new list in random order")
def _shuffle(items):
    items = list(items)
    _random.shuffle(items)
    return items


@builtin("seed", C, "seed(n) makes random results repeatable")
def _seed(n):
    _random.seed(n)


# ---- lists ----
@builtin("range", C, "range(a, b, step=1) list from a to b (b included)")
def _range(a, b=None, step=1):
    if b is None:
        a, b = 0, a - 1
    if step == 0:
        raise EchoRuntimeError("step can't be 0.")
    out, i = [], a
    while (i <= b) if step > 0 else (i >= b):
        out.append(i)
        i += step
        if len(out) > 10_000_000:
            raise EchoRuntimeError("range() is too big.")
    return out


@builtin("append", C, "append(list, item) adds to the end", aliases=("push",))
def _append(items, value):
    items.append(value)
    return items


@builtin("pop", C, "pop(list, position=-1) removes and returns an item")
def _pop(items, pos=-1):
    if not items:
        raise EchoRuntimeError("pop() from an empty list.")
    return items.pop(int(pos))


@builtin("insert", C, "insert(list, position, item)")
def _insert(items, pos, value):
    items.insert(int(pos), value)
    return items


@builtin("remove", C, "remove(list or map, item or key)")
def _remove(items, value):
    if isinstance(items, dict):
        items.pop(value, None)
    elif value in items:
        items.remove(value)
    return items


@builtin("sort", C, "sort(list, key=nothing, reverse=false) new sorted list", needs_interp=True)
def _sort(interp, items, key=None, reverse=False):
    items = list(_list(items, "sort"))
    try:
        if key is None:
            return sorted(items, reverse=bool(reverse))
        return sorted(items, key=lambda x: interp.call_value(key, [x]), reverse=bool(reverse))
    except TypeError:
        raise EchoRuntimeError("sort() can't compare these items (mixed numbers and text?).")


@builtin("reverse", C, "reverse(list or text)")
def _reverse(items):
    return items[::-1]


@builtin("map", C, "map(list, fn) applies fn to each item", needs_interp=True)
def _map(interp, items, fn):
    return [interp.call_value(fn, [x]) for x in _list(items, "map")]


@builtin("filter", C, "filter(list, fn) keeps items where fn is true", needs_interp=True)
def _filter(interp, items, fn):
    out = []
    for x in _list(items, "filter"):
        keep = interp.call_value(fn, [x])
        if not isinstance(keep, bool):
            raise EchoRuntimeError("filter() needs a function that returns true or false, not %s." % type_name(keep),
                                   code="E303")
        if keep:
            out.append(x)
    return out


@builtin("reduce", C, "reduce(list, fn, start)", needs_interp=True)
def _reduce(interp, items, fn, start=None):
    items = list(items)
    acc = start
    if acc is None:
        if not items:
            raise EchoRuntimeError("reduce() of an empty list needs a start value.")
        acc, items = items[0], items[1:]
    for x in items:
        acc = interp.call_value(fn, [acc, x])
    return acc


@builtin("unique", C, "unique(list) without repeats, order kept")
def _unique(items):
    out = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


@builtin("zip", C, "zip(a, b) pairs items: [[a0, b0], ...]")
def _zip(a, b):
    return [[x, y] for x, y in zip(a, b)]


@builtin("index_of", C, "index_of(list or text, item) position or -1")
def _index_of(items, value):
    if isinstance(items, str):
        return items.find(value)
    return items.index(value) if value in items else -1


@builtin("count", C, "count(list or text, item)")
def _count(items, value):
    return items.count(value)


@builtin("slice", C, "slice(x, start, end) part of a list or text")
def _slice(items, a, b=None):
    return items[int(a):None if b is None else int(b)]


@builtin("flatten", C, "flatten(list of lists)")
def _flatten(items):
    out = []
    for x in items:
        out.extend(x if isinstance(x, list) else [x])
    return out


# ---- text ----
@builtin("upper", C, "upper(text)")
def _upper(s):
    return show(s).upper()


@builtin("lower", C, "lower(text)")
def _lower(s):
    return show(s).lower()


@builtin("trim", C, "trim(text) removes spaces at both ends")
def _trim(s):
    return show(s).strip()


@builtin("split", C, "split(text, separator=spaces)")
def _split(s, sep=None):
    if sep is None:
        return show(s).split()
    if sep == "":
        return list(show(s))
    return show(s).split(show(sep))


@builtin("join", C, "join(list, separator='')")
def _join(items, sep=""):
    return show(sep).join(show(x) for x in items)


@builtin("replace", C, "replace(text, old, new)")
def _replace(s, old, new):
    return show(s).replace(show(old), show(new))


@builtin("contains", C, "contains(text or list, item)")
def _contains(items, value):
    return value in items


@builtin("starts_with", C, "starts_with(text, start)")
def _starts(s, p):
    return show(s).startswith(show(p))


@builtin("ends_with", C, "ends_with(text, end)")
def _ends(s, p):
    return show(s).endswith(show(p))


@builtin("find", C, "find(text, part) first position or -1")
def _find(s, part):
    return show(s).find(show(part))


@builtin("pad", C, "pad(text, width, fill=' ') pads on the right (negative width pads left)")
def _pad(s, width, fill=" "):
    s, width = show(s), int(width)
    return s.rjust(-width, fill) if width < 0 else s.ljust(width, fill)


@builtin("format", C, "format(number, places) fixed decimals as text")
def _format(x, places=2):
    return "%.*f" % (int(places), _num(x, "format"))


@builtin("chars", C, "chars(text) list of letters")
def _chars(s):
    return list(show(s))


@builtin("code", C, "code(letter) character code")
def _code(ch):
    return ord(show(ch)[0])


@builtin("letter", C, "letter(code) character from code")
def _letter(n):
    return chr(int(n))


# ---- maps ----
@builtin("keys", C, "keys(map)")
def _keys(m):
    return [k for k in m if k != "_type"]


@builtin("values", C, "values(map)")
def _values(m):
    return [v for k, v in m.items() if k != "_type"]


@builtin("has", C, "has(map, key)")
def _has(m, key):
    return key in m


@builtin("get", C, "get(map or list, key, default=nothing)")
def _get(m, key, default=None):
    if isinstance(m, dict):
        return m.get(key, default)
    try:
        return m[int(key)]
    except (IndexError, ValueError, TypeError):
        return default


@builtin("copy", C, "copy(list or map) a separate copy")
def _copy(v):
    return json.loads(json.dumps(v)) if isinstance(v, (list, dict)) else v


# ---- files and data ----
@builtin("read_file", C, "read_file(path) text of a file")
def _read_file(path):
    with open(show(path), encoding="utf-8") as f:
        return f.read()


@builtin("write_file", C, "write_file(path, text)")
def _write_file(path, text):
    with open(show(path), "w", encoding="utf-8") as f:
        f.write(show(text))
    return True


@builtin("append_file", C, "append_file(path, text)")
def _append_file(path, text):
    with open(show(path), "a", encoding="utf-8") as f:
        f.write(show(text))
    return True


@builtin("file_exists", C, "file_exists(path)")
def _exists(path):
    return os.path.exists(show(path))


@builtin("from_json", C, "from_json(text) map/list from JSON")
def _from_json(text):
    return json.loads(text)


@builtin("to_json", C, "to_json(value) JSON text")
def _to_json(v):
    return json.dumps(v, indent=2)


@builtin("read_csv", C, "read_csv(path) list of maps (first row is the header)")
def _read_csv(path):
    import csv
    with open(show(path), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        row = {}
        for k, v in r.items():
            try:
                row[k] = int(v)
            except (ValueError, TypeError):
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    row[k] = v
        out.append(row)
    return out


# ---- time ----
@builtin("now", C, "now() date and time as text")
def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


@builtin("today", C, "today() date as text")
def _today():
    return time.strftime("%Y-%m-%d")


@builtin("clock", C, "clock() seconds, for timing code")
def _clock():
    return time.perf_counter()


@builtin("wait", C, "wait(seconds)", aliases=("sleep",))
def _wait(seconds):
    time.sleep(min(float(seconds), 60))


@builtin("help", C, "help() lists everything; help(\"bio\") lists a module; help(\"bio.gc\") explains one function",
         needs_interp=True)
def _help(interp, name=None):
    from ..modules import GLOBALS, MODULES
    from ..values import Builtin, Module

    def line(qual, value):
        doc = value.doc if isinstance(value, Builtin) else ""
        return "  " + (doc or "%s = %s" % (qual, show(value, True)))

    if name is None:
        interp.output("Global functions:")
        interp.output("  " + ", ".join(sorted(GLOBALS)))
        interp.output("Modules (write module.function):")
        for mname in sorted(MODULES):
            interp.output("  %-7s %s" % (mname, MODULES[mname].doc))
        interp.output('Try help("bio") or help("bio.gc").')
        return None
    name = show(name)
    if name in MODULES:
        mod = MODULES[name]
        interp.output("%s: %s" % (name, mod.doc))
        for member in sorted(mod.members):
            interp.output(line(name + "." + member, mod.members[member]))
        return None
    if "." in name:
        mname, member = name.split(".", 1)
        mod = MODULES.get(mname)
        if mod and member in mod.members:
            interp.output(line(name, mod.members[member]))
            return None
    elif name in GLOBALS:
        interp.output(line(name, GLOBALS[name]))
        return None
    interp.output("Nothing called %s. Run help() to see everything." % name)
