"""`echolang upgrade FILE`: rewrites Echo 1 code as Echo 2.

It handles the mechanical changes (set ... to, true/false, ==, modules, method calls, 'of' calls, then, each,
break/continue, double quotes, one statement per line). Anything it can't decide is left for `echolang check`.
"""
import re

from .lexer import Token, tokenize

OPENER_WORDS = {"if", "repeat", "while", "for", "define", "try"}
OLD_ASSIGN = {"=", "+=", "-=", "*=", "/="}
OLD_ALIASES = {"len": "length", "size": "length", "str": "text", "num": "number", "gc_content": "gc",
               "at_content": "at", "count_bases": "base_counts", "revcomp": "reverse_complement",
               "pi_of": "isoelectric_point", "push": "append", "sleep": "wait", "average": "mean", "sd": "stdev"}


# ------------------------------------------------------------------ text level (before tokenizing)
def _fix_quotes_and_semicolons(source):
    out, i, n = [], 0, len(source)
    line_start = 0
    while i < n:
        ch = source[i]
        if ch == "\n":
            line_start = len(out) + 1
            out.append(ch)
            i += 1
        elif ch == "#":
            j = source.find("\n", i)
            j = n if j < 0 else j
            out.append(source[i:j])
            i = j
        elif source.startswith('"""', i) or source.startswith("'''", i):
            q = source[i:i + 3]
            j = source.find(q, i + 3)
            j = n if j < 0 else j
            body = source[i + 3:j]
            out.append('"""' + body.replace('"""', '\\"\\"\\"') + '"""')
            i = j + 3
        elif ch in "\"'":
            j = i + 1
            buf = []
            while j < n and source[j] != ch and source[j] != "\n":
                if source[j] == "\\" and j + 1 < n:
                    pair = source[j:j + 2]
                    buf.append("'" if pair == "\\'" else pair)
                    j += 2
                    continue
                buf.append('\\"' if source[j] == '"' else source[j])
                j += 1
            out.append('"' + "".join(buf) + '"')
            i = j + 1
        elif ch == ";":
            current = "".join(out)[line_start:]
            indent = re.match(r"[ \t]*", current).group(0)
            out.append("\n" + indent)
            i += 1
            while i < n and source[i] in " \t":
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# ------------------------------------------------------------------ helpers
def _tok(kind, value, raw=None):
    return Token(kind, value, 0, raw if raw is not None else value)


def _is(t, kind, *values):
    return t is not None and t.kind == kind and (not values or t.value in values)


def _match_forward(toks, i):
    pairs = {"(": ")", "[": "]", "{": "}"}
    opener, closer, depth = toks[i].value, pairs[toks[i].value], 0
    for k in range(i, len(toks)):
        if _is(toks[k], "OP", opener):
            depth += 1
        elif _is(toks[k], "OP", closer):
            depth -= 1
            if depth == 0:
                return k
    return len(toks) - 1


def _match_back(toks, i):
    pairs = {")": "(", "]": "[", "}": "{"}
    closer, opener, depth = toks[i].value, pairs[toks[i].value], 0
    for k in range(i, -1, -1):
        if _is(toks[k], "OP", closer):
            depth += 1
        elif _is(toks[k], "OP", opener):
            depth -= 1
            if depth == 0:
                return k
    return 0


def _new_name(name):
    """Echo 1 built-in name -> Echo 2 name (may contain a dot), or None."""
    from .modules import QUALNAME, build
    build()
    internal = OLD_ALIASES.get(name, name)
    return QUALNAME.get(internal)


def _qual_tokens(qual):
    if "." in qual:
        m, n = qual.split(".", 1)
        return [_tok("NAME", m), _tok("OP", "."), _tok("NAME", n)]
    return [_tok("NAME", qual)]


def _postfix_end(toks, i):
    """Index just after one Echo 1 postfix expression starting at i."""
    if i >= len(toks):
        return i
    if _is(toks[i], "OP", "(", "[", "{"):
        i = _match_forward(toks, i) + 1
    elif toks[i].kind in ("NAME", "NUMBER", "STRING", "KEYWORD"):
        i += 1
    else:
        return i
    while i < len(toks):
        if _is(toks[i], "OP", "(", "["):
            i = _match_forward(toks, i) + 1
        elif _is(toks[i], "OP", ".") and i + 1 < len(toks):
            i += 2
        else:
            break
    return i


def _receiver_start(toks, j):
    k, start = j - 1, j
    while k >= 0:
        t = toks[k]
        if _is(t, "OP", ")", "]"):
            start = _match_back(toks, k)
            k = start - 1
            continue
        if t.kind in ("NAME", "STRING", "NUMBER") or _is(t, "KEYWORD", "true", "false", "nothing"):
            start = k
            if k - 1 >= 0 and _is(toks[k - 1], "OP", "."):
                k -= 2
                continue
        break
    return start


# ------------------------------------------------------------------ expression rewrites
def _rewrite_expr(toks, user_names, notes):
    toks = list(toks)
    # strings: rewrite code inside {...}
    for t in toks:
        if t.kind == "STRING" and t.raw and "{" in t.raw:
            t.raw = _rewrite_string(t.raw, user_names, notes)
    # 'is not' / 'is'
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if _is(t, "KEYWORD", "is"):
            if i + 1 < len(toks) and _is(toks[i + 1], "KEYWORD", "not"):
                out.append(_tok("OP", "!="))
                i += 2
                continue
            out.append(_tok("OP", "=="))
            i += 1
            continue
        if _is(t, "NAME", "yes", "no") and t.value not in user_names:
            out.append(_tok("KEYWORD", "true" if t.value == "yes" else "false"))
            i += 1
            continue
        out.append(t)
        i += 1
    toks = out
    # 'f of x' -> f(x)
    changed = True
    while changed:
        changed = False
        for i, t in enumerate(toks):
            if _is(t, "NAME", "of") and i > 0 and toks[i - 1].kind == "NAME" and i + 1 < len(toks) and \
                    not _is(toks[i + 1], "OP"):
                end = _postfix_end(toks, i + 1)
                toks = toks[:i] + [_tok("OP", "(")] + toks[i + 1:end] + [_tok("OP", ")")] + toks[end:]
                changed = True
                break
    # value.method(args) -> function(value, args)
    changed = True
    while changed:
        changed = False
        for j, t in enumerate(toks):
            if _is(t, "OP", ".") and j + 2 < len(toks) and toks[j + 1].kind == "NAME" and \
                    _is(toks[j + 2], "OP", "(") and j > 0:
                name = toks[j + 1].value
                qual = _new_name(name)
                if qual is None or name in user_names:
                    continue
                start = _receiver_start(toks, j)
                first = toks[start]
                if first.kind == "NAME" and first.value in _module_names() and start == j - 1:
                    continue  # already a module call
                close = _match_forward(toks, j + 2)
                receiver = toks[start:j]
                args = toks[j + 3:close]
                new = _qual_tokens(qual) + [_tok("OP", "(")] + receiver + \
                    ([_tok("OP", ","), ] + args if args else []) + [_tok("OP", ")")]
                toks = toks[:start] + new + toks[close + 1:]
                changed = True
                break
    # built-in names -> module names
    out = []
    for i, t in enumerate(toks):
        prev = toks[i - 1] if i > 0 else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.kind == "NAME" and t.value not in user_names and not _is(prev, "OP", ".") and \
                not _is(nxt, "OP", ":") and t.value not in _module_names():
            if t.value in ("print",) and _is(nxt, "OP", "("):
                out.append(t)
                continue
            qual = _new_name(t.value)
            if qual and qual != t.value:
                out.extend(_qual_tokens(qual))
                continue
        out.append(t)
    return out


_MODS = None


def _module_names():
    global _MODS
    if _MODS is None:
        from .modules import MODULES, build
        build()
        _MODS = set(MODULES)
    return _MODS


def _rewrite_string(raw, user_names, notes):
    def fix(m):
        inner = m.group(1)
        try:
            toks = [t for t in tokenize(inner) if t.kind not in ("NEWLINE", "EOF")]
        except Exception:
            return m.group(0)
        from .formatter import format_line
        return "{" + format_line(_rewrite_expr(toks, user_names, notes), 0) + "}"
    return re.sub(r"(?<!\\)\{([^{}]+)\}", fix, raw)


# ------------------------------------------------------------------ statements
def _user_names(lines):
    names = set()
    for toks in lines:
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if _is(t, "KEYWORD", "set", "into", "catch", "define", "record", "global", "each", "for") and \
                    nxt is not None and nxt.kind == "NAME":
                names.add(nxt.value)
                if t.value in ("each", "for") and i + 3 < len(toks) and _is(toks[i + 2], "OP", ","):
                    names.add(toks[i + 3].value)
            if _is(t, "KEYWORD", "define", "record") and nxt is not None:
                k = i + 2
                if k < len(toks) and _is(toks[k], "OP", "("):
                    close = _match_forward(toks, k)
                    for p in range(k + 1, close):
                        if toks[p].kind == "NAME" and (_is(toks[p - 1], "OP", "(", ",")):
                            names.add(toks[p].value)
        if toks and toks[0].kind == "NAME" and len(toks) > 1 and _is(toks[1], "OP", *OLD_ASSIGN):
            names.add(toks[0].value)
    names.discard("ai")
    return names


def _top_level_op(toks, ops):
    depth = 0
    for i, t in enumerate(toks):
        if _is(t, "OP", "(", "[", "{"):
            depth += 1
        elif _is(t, "OP", ")", "]", "}"):
            depth -= 1
        elif depth == 0 and _is(t, "OP", *ops):
            return i
    return -1


def _strip_comment(toks):
    if toks and toks[-1].kind == "COMMENT":
        return toks[:-1], [toks[-1]]
    return toks, []


def _statement(toks, notes, line_no):
    """Rewrite one statement's tokens. Returns a list of token lists (usually one)."""
    toks, comment = _strip_comment(toks)
    if not toks:
        return [comment]
    first = toks[0]
    if len(toks) == 1 and _is(first, "NAME", "pass"):
        return [comment] if comment else []
    if len(toks) == 1 and _is(first, "NAME", "stop", "skip"):
        return [[_tok("KEYWORD", "break" if first.value == "stop" else "continue")] + comment]
    if _is(first, "KEYWORD", "end") and len(toks) == 2 and _is(toks[1], "KEYWORD", *OPENER_WORDS):
        return [[first] + comment]
    if _is(first, "KEYWORD", "repeat") and len(toks) == 2 and _is(toks[1], "NAME", "forever"):
        return [[_tok("KEYWORD", "while"), _tok("KEYWORD", "true")] + comment]
    if _is(first, "KEYWORD", "for") and len(toks) > 2 and toks[1].kind == "NAME" and \
            (_is(toks[2], "KEYWORD", "in") or _is(toks[2], "OP", ",")):
        toks = [first, _tok("KEYWORD", "each")] + toks[1:]
    if _is(first, "KEYWORD", "if") or (_is(first, "KEYWORD", "else") and len(toks) > 1 and _is(toks[1], "KEYWORD", "if")):
        if not _is(toks[-1], "KEYWORD", "then"):
            toks = toks + [_tok("KEYWORD", "then")]
    if _is(first, "KEYWORD", "use") and len(toks) == 2 and toks[1].kind == "NAME":
        return [comment] if comment else []
    if _is(first, "KEYWORD", "use") and len(toks) >= 2 and toks[1].kind == "STRING":
        notes.append("line %d: functions from %s are now used as module.function(...)" % (line_no, toks[1].raw))
    if _is(first, "KEYWORD", "ask") and len(toks) > 1 and _is(toks[1], "NAME", "ai"):
        into = next((i for i, t in enumerate(toks) if _is(t, "KEYWORD", "into")), -1)
        question = toks[2:into] if into > 0 else toks[2:]
        call = [_tok("NAME", "ai"), _tok("OP", "."), _tok("NAME", "ask"), _tok("OP", "(")] + question + \
            [_tok("OP", ")")]
        if into > 0:
            return [[_tok("KEYWORD", "set"), toks[into + 1], _tok("KEYWORD", "to")] + call + comment]
        return [[_tok("KEYWORD", "say")] + call + comment]
    if _is(first, "NAME", "print") and len(toks) > 2 and _is(toks[1], "OP", "(") and \
            _match_forward(toks, 1) == len(toks) - 1:
        return [[_tok("KEYWORD", "say")] + toks[2:-1] + comment]
    # assignments
    body = toks[1:] if _is(first, "KEYWORD", "set") else toks
    k = _top_level_op(body, OLD_ASSIGN)
    if k > 0 and (_is(first, "KEYWORD", "set") or first.kind == "NAME"):
        target, op, value = body[:k], body[k].value, body[k + 1:]
        if op == "=":
            new_value = value
        else:
            simple = len(value) == 1
            new_value = target + [_tok("OP", op[0])] + (value if simple else
                                                          [_tok("OP", "(")] + value + [_tok("OP", ")")])
        return [[_tok("KEYWORD", "set")] + target + [_tok("KEYWORD", "to")] + new_value + comment]
    return [toks + comment]


def upgrade_source(source):
    """Returns (new_source, notes). notes lists things a person should look at."""
    from .formatter import format_line, format_source
    notes = []
    text = _fix_quotes_and_semicolons(source)
    tokens = tokenize(text, keep_comments=True)
    lines, cur = [], []
    for t in tokens:
        if t.kind in ("NEWLINE", "EOF"):
            if cur:
                lines.append(cur)
            cur = []
            continue
        cur.append(t)
    user_names = _user_names(lines)
    out_lines = []
    last_line = None
    catch_vars = []   # stack of (name, depth) for catch blocks
    depth = 0
    for toks in lines:
        line_no = toks[0].line
        if last_line is not None and line_no - last_line > 1:
            out_lines.append([])
        last_line = max(t.line + (t.raw.count("\n") if t.kind == "STRING" and t.raw else 0) for t in toks)
        for st in _statement(toks, notes, line_no):
            st = _rewrite_expr(st, user_names, notes)
            head = st[0] if st else None
            if _is(head, "KEYWORD", "end"):
                depth -= 1
                while catch_vars and catch_vars[-1][1] > depth:
                    catch_vars.pop()
            if catch_vars:
                names = {c[0] for c in catch_vars}
                fixed = []
                for i, t in enumerate(st):
                    nxt = st[i + 1] if i + 1 < len(st) else None
                    prev = st[i - 1] if i > 0 else None
                    if t.kind == "NAME" and t.value in names and not _is(nxt, "OP", ".") and \
                            not _is(prev, "OP", "."):
                        fixed += [t, _tok("OP", "."), _tok("NAME", "message")]
                    else:
                        fixed.append(t)
                    if t.kind == "STRING" and t.raw:
                        for n in names:
                            t.raw = re.sub(r"\{%s\}" % re.escape(n), "{%s.message}" % n, t.raw)
                st = fixed
            if _is(head, "KEYWORD", "catch") and len(st) > 1 and st[1].kind == "NAME":
                catch_vars.append((st[1].value, depth))
            if _is(head, "KEYWORD", *OPENER_WORDS):
                depth += 1
            out_lines.append(st)
    text = "\n".join(format_line(st, 0) if st else "" for st in out_lines)
    try:
        return format_source(text), notes
    except Exception as e:  # leave it unformatted rather than lose work
        notes.append("could not format the result: %s" % e)
        return text + "\n", notes
