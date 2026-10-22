"""Logic gates and bits. The operators and, or, not, xor, nand, nor, xnor are part of the language;
these functions add truth tables, adders and bit tools."""
from ..errors import EchoRuntimeError
from ..values import show, truthy
from . import builtin

G = "gates"

GATES = {
    "and": lambda a, b: a and b, "or": lambda a, b: a or b, "xor": lambda a, b: a != b,
    "nand": lambda a, b: not (a and b), "nor": lambda a, b: not (a or b), "xnor": lambda a, b: a == b,
}


def _b(v):
    return 1 if truthy(v) else 0


@builtin("gate", G, "gate(name, a, b) runs a gate by name: and, or, xor, nand, nor, xnor, not")
def _gate(name, a, b=None):
    name = show(name).lower()
    if name == "not":
        return 1 - _b(a)
    if name not in GATES:
        raise EchoRuntimeError("Unknown gate '%s'." % name, hint="Use and, or, not, xor, nand, nor or xnor.")
    return 1 if GATES[name](bool(_b(a)), bool(_b(b))) else 0


@builtin("truth_table", G, "truth_table(fn or gate name, inputs=2) table of every input combination (show it with say)",
         needs_interp=True)
def _truth_table(interp, fn, inputs=None):
    if isinstance(fn, str):
        name = fn.lower()
        n = 1 if name == "not" else 2
        call = lambda bits: _gate(name, *bits)
        title = name.upper()
    else:
        if inputs:
            n = int(inputs)
        elif hasattr(fn, "params"):
            n = len(fn.params) or 2
        elif hasattr(fn, "builtin"):
            n = 2
        else:
            import inspect
            try:
                n = len(inspect.signature(getattr(fn, "fn", fn)).parameters) or 2
            except (TypeError, ValueError):
                n = 2
        call = lambda bits: interp.call_value(fn, list(bits))
        title = (getattr(fn, "name", None) or getattr(fn, "__name__", "fn")).lstrip("_")
    letters = "ABCDEFGH"[:n]
    lines = [" ".join(letters) + " | " + title, "-" * (2 * n) + "+" + "-" * (len(title) + 1)]
    rows = []
    for i in range(2 ** n):
        bits = [(i >> (n - 1 - k)) & 1 for k in range(n)]
        out = call(bits)
        if isinstance(out, dict):
            out_s = " ".join("%s=%s" % (k, _b(v)) for k, v in out.items())
        else:
            out_s = str(_b(out))
        lines.append(" ".join(str(b) for b in bits) + " | " + out_s)
        rows.append(bits + [out])
    return "\n".join(lines)


@builtin("half_adder", G, "half_adder(a, b) -> {sum, carry}")
def _half_adder(a, b):
    a, b = _b(a), _b(b)
    return {"sum": a ^ b, "carry": a & b}


@builtin("full_adder", G, "full_adder(a, b, carry_in) -> {sum, carry}")
def _full_adder(a, b, c):
    a, b, c = _b(a), _b(b), _b(c)
    return {"sum": a ^ b ^ c, "carry": (a & b) | (c & (a ^ b))}


@builtin("add_binary", G, "add_binary('1011', '0110') adds two binary numbers with full adders")
def _add_binary(x, y):
    x, y = show(x), show(y)
    if set(x + y) - set("01"):
        raise EchoRuntimeError("add_binary() needs text made of 0 and 1.")
    n = max(len(x), len(y))
    x, y = x.zfill(n), y.zfill(n)
    carry, out = 0, []
    for i in range(n - 1, -1, -1):
        r = _full_adder(int(x[i]), int(y[i]), carry)
        out.append(str(r["sum"]))
        carry = r["carry"]
    if carry:
        out.append("1")
    return "".join(reversed(out))


def _int(v, f):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
        raise EchoRuntimeError("%s() needs whole numbers." % f)
    return int(v)


@builtin("bit_and", G, "bit_and(a, b) bitwise AND")
def _band(a, b):
    return _int(a, "bit_and") & _int(b, "bit_and")


@builtin("bit_or", G, "bit_or(a, b) bitwise OR")
def _bor(a, b):
    return _int(a, "bit_or") | _int(b, "bit_or")


@builtin("bit_xor", G, "bit_xor(a, b) bitwise XOR")
def _bxor(a, b):
    return _int(a, "bit_xor") ^ _int(b, "bit_xor")


@builtin("bit_not", G, "bit_not(a, bits=8) flips every bit")
def _bnot(a, bits=8):
    return (~_int(a, "bit_not")) & ((1 << int(bits)) - 1)


@builtin("shift_left", G, "shift_left(a, n)")
def _shl(a, n):
    return _int(a, "shift_left") << int(n)


@builtin("shift_right", G, "shift_right(a, n)")
def _shr(a, n):
    return _int(a, "shift_right") >> int(n)


@builtin("to_binary", G, "to_binary(n, bits=0) binary text, padded to bits")
def _to_binary(n, bits=0):
    n = _int(n, "to_binary")
    if n < 0:
        raise EchoRuntimeError("to_binary() needs a number 0 or above.")
    return format(n, "b").zfill(int(bits))


@builtin("from_binary", G, "from_binary('1011') -> 11")
def _from_binary(s):
    return int(show(s).replace(" ", ""), 2)


@builtin("to_hex", G, "to_hex(n) hexadecimal text")
def _to_hex(n):
    return format(_int(n, "to_hex"), "x")


@builtin("from_hex", G, "from_hex('ff') -> 255")
def _from_hex(s):
    return int(show(s).replace("0x", ""), 16)


@builtin("count_ones", G, "count_ones(n) how many 1 bits")
def _count_ones(n):
    return bin(_int(n, "count_ones")).count("1")
