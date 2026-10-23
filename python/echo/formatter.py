"""`echolang fmt`: rewrites Echo code in the one standard layout.

- 4 spaces per block level, `end`, `else` and `catch` line up with their opener
- one space around operators and after commas; none inside brackets
- comments kept; at most one blank line in a row; one newline at the end of the file
"""
from .lexer import tokenize

OPENERS = {"if", "while", "for", "repeat", "define", "try"}
MIDDLES = {"else", "catch"}
BINARY = {"+", "-", "*", "/", "//", "%", "^", "==", "!=", "<", ">", "<=", ">=", "->", "=", "+=", "-=", "*=", "/="}
WORD_OPS = {"and", "or", "not", "xor", "nand", "nor", "xnor", "in", "to", "from", "step", "into", "as", "then",
            "times", "each"}
VALUE_KEYWORDS = {"true", "false", "nothing"}
INDENT = "    "


def _end_line(tok):
    return tok.line + (tok.raw.count("\n") if tok.kind == "STRING" and tok.raw else 0)


def _lines(tokens):
    lines, cur = [], []
    for t in tokens:
        if t.kind == "EOF":
            break
        if t.kind == "NEWLINE":
            if cur:
                lines.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur:
        lines.append(cur)
    return lines


def _text(t):
    if t.kind == "KEYWORD" or t.kind == "NAME" or t.kind == "OP":
        return t.value
    return t.raw if t.raw is not None else str(t.value)


def _is_value_end(t):
    """Token that can end a value (so a following ( or [ is a call or index)."""
    if t.kind in ("NAME", "NUMBER", "STRING"):
        return True
    if t.kind == "KEYWORD" and t.value in VALUE_KEYWORDS:
        return True
    return t.kind == "OP" and t.value in (")", "]", "}")


def format_line(tokens, level):
    """Lay out one logical line. Returns text (may contain newlines for multi-line brackets)."""
    out = []
    stack = []          # open brackets
    prev = prev_prev = None
    unary_next = False
    for i, t in enumerate(tokens):
        if t.kind == "SOFTNL":
            if out and out[-1] == "\n":
                continue
            if out:
                out[-1] = out[-1].rstrip(" ")
            out.append("\n")
            prev_prev, prev = prev, t
            continue
        if t.kind == "COMMENT":
            if prev is None or prev.kind == "SOFTNL":
                if prev is not None:
                    out.append(INDENT * (level + len(stack)))
                out.append(t.raw)
            else:
                out.append("  " + t.raw)
            prev_prev, prev = prev, t
            continue
        text = _text(t)
        space = True
        if prev is None:
            space = False
        elif prev.kind == "SOFTNL":
            close = t.kind == "OP" and t.value in (")", "]", "}")
            out.append(INDENT * (level + len(stack) - (1 if close else 0)))
            space = False
        elif t.kind == "OP":
            v = t.value
            if v in (")", "]", "}", ",", "."):
                space = False
            elif v == ":":
                space = False
            elif v in ("(", "["):
                member = prev_prev is not None and prev_prev.kind == "OP" and prev_prev.value == "."
                space = not (_is_value_end(prev) or member) and not (prev.kind == "KEYWORD" and prev.value == "fn")
            if prev.kind == "OP" and prev.value in ("(", "[", "{", "."):
                space = False
            if prev.kind == "OP" and prev.value == ":" and stack and stack[-1] == "[":
                space = False
        else:
            if prev.kind == "OP" and prev.value in ("(", "[", "{", "."):
                space = False
            elif prev.kind == "OP" and prev.value == ":" and stack and stack[-1] == "[":
                space = False
        if unary_next:
            space = False
            unary_next = False
        if t.kind == "OP" and t.value == ":" and stack and stack[-1] == "[":
            space = False
        if space and out and not out[-1].endswith(("\n", " ")):
            out.append(" ")
        out.append(text)
        # a minus that starts a value is unary: no space after it
        if t.kind == "OP" and t.value == "-":
            if prev is None or prev.kind == "SOFTNL" or (prev.kind == "OP" and prev.value not in (")", "]", "}")) or \
                    (prev.kind == "KEYWORD" and prev.value not in VALUE_KEYWORDS):
                unary_next = True
        if t.kind == "OP" and t.value in ("(", "[", "{"):
            stack.append(t.value)
        elif t.kind == "OP" and t.value in (")", "]", "}") and stack:
            stack.pop()
        prev_prev, prev = prev, t
    return "".join(out).rstrip(" ")


def format_source(source):
    """Return the formatted text. Raises EchoSyntaxError if the code can't be read."""
    tokens = tokenize(source, keep_comments=True)
    lines = _lines(tokens)
    out = []
    level = 0
    last_end_line = None
    for toks in lines:
        first = next((t for t in toks if t.kind not in ("SOFTNL",)), None)
        if first is None:
            continue
        if last_end_line is not None and first.line - last_end_line > 1 and out:
            out.append("")
        head = first.value if first.kind == "KEYWORD" else None
        if head == "end" or head in MIDDLES:
            level = max(0, level - 1)
        text = format_line(toks, level)
        out.append(INDENT * level + text)
        if head in OPENERS or head in MIDDLES:
            level += 1
        last_end_line = max(_end_line(t) for t in toks)
    result = "\n".join(out).rstrip() + "\n"
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    return result


def is_formatted(source):
    try:
        return format_source(source) == source
    except Exception:
        return False
