"""Turns Echo source text into tokens."""
from .errors import EchoSyntaxError

KEYWORDS = {
    "set", "to", "say", "ask", "into", "if", "then", "else", "end", "repeat", "times",
    "while", "for", "each", "in", "from", "step", "break", "continue", "stop", "skip",
    "define", "return", "try", "catch", "fail", "use", "record", "fn", "add",
    "and", "or", "not", "xor", "nand", "nor", "xnor", "is",
    "true", "false", "yes", "no", "nothing", "global", "pass",
}

# longest first
OPERATORS = [
    "->", "==", "!=", "<=", ">=", "+=", "-=", "*=", "/=", "//",
    "+", "-", "*", "/", "%", "^", "<", ">", "=", "(", ")", "[", "]", "{", "}",
    ",", ".", ":",
]


class Token:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind = kind      # NUMBER STRING NAME KEYWORD OP NEWLINE EOF
        self.value = value
        self.line = line

    def __repr__(self):
        return "Token(%s, %r, %d)" % (self.kind, self.value, self.line)


ESCAPES = {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\", "{": "{", "}": "}", "0": "\0"}


def _string_parts(raw, line):
    """Split string text into literal parts and {expression} parts."""
    parts, buf, i = [], [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            buf.append(ESCAPES.get(nxt, "\\" + nxt))
            i += 2
            continue
        if ch == "{":
            depth, j = 1, i + 1
            while j < len(raw) and depth:
                if raw[j] == "{":
                    depth += 1
                elif raw[j] == "}":
                    depth -= 1
                j += 1
            if depth:
                raise EchoSyntaxError("A '{' in this text has no closing '}'.", line,
                                      "Write \\{ if you want a real curly bracket.")
            if buf:
                parts.append(("text", "".join(buf)))
                buf = []
            expr = raw[i + 1:j - 1].strip()
            if not expr:
                raise EchoSyntaxError("Empty {} in text.", line)
            parts.append(("expr", expr, line))
            i = j
            continue
        buf.append(ch)
        i += 1
    if buf or not parts:
        parts.append(("text", "".join(buf)))
    return parts


def tokenize(source):
    tokens = []
    i, line, depth = 0, 1, 0
    n = len(source)

    def add(kind, value):
        tokens.append(Token(kind, value, line))

    while i < n:
        ch = source[i]
        if ch == "#":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "\n":
            if depth == 0 and tokens and tokens[-1].kind != "NEWLINE":
                add("NEWLINE", "\n")
            line += 1
            i += 1
            continue
        if ch in " \t\r":
            i += 1
            continue
        if ch == ";":
            if tokens and tokens[-1].kind != "NEWLINE":
                add("NEWLINE", ";")
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            j = i
            seen_dot = False
            while j < n and (source[j].isdigit() or source[j] == "_" or (source[j] == "." and not seen_dot
                                                                          and j + 1 < n and source[j + 1].isdigit())):
                if source[j] == ".":
                    seen_dot = True
                j += 1
            if j < n and source[j] in "eE" and j + 1 < n and (source[j + 1].isdigit() or
                                                              (source[j + 1] in "+-" and j + 2 < n and source[j + 2].isdigit())):
                j += 2
                while j < n and source[j].isdigit():
                    j += 1
                seen_dot = True
            text = source[i:j].replace("_", "")
            add("NUMBER", float(text) if seen_dot else int(text))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            add("KEYWORD" if word in KEYWORDS else "NAME", word)
            i = j
            continue
        if ch in "\"'":
            start_line = line
            if source.startswith(ch * 3, i):
                end = source.find(ch * 3, i + 3)
                if end < 0:
                    raise EchoSyntaxError("This long text has no closing %s." % (ch * 3), start_line)
                raw = source[i + 3:end]
                line += raw.count("\n")
                i = end + 3
            else:
                j = i + 1
                buf = []
                while j < n and source[j] != ch:
                    if source[j] == "\n":
                        raise EchoSyntaxError("Text is missing its closing quote %s." % ch, start_line,
                                              "Use triple quotes for text that spans lines.")
                    if source[j] == "\\" and j + 1 < n:
                        buf.append(source[j:j + 2])
                        j += 2
                        continue
                    buf.append(source[j])
                    j += 1
                if j >= n:
                    raise EchoSyntaxError("Text is missing its closing quote %s." % ch, start_line)
                raw = "".join(buf)
                i = j + 1
            tokens.append(Token("STRING", _string_parts(raw, start_line), start_line))
            continue
        for op in OPERATORS:
            if source.startswith(op, i):
                if op in "([{":
                    depth += 1
                elif op in ")]}":
                    depth = max(0, depth - 1)
                add("OP", op)
                i += len(op)
                break
        else:
            raise EchoSyntaxError("I don't understand the character %r." % ch, line)
    if tokens and tokens[-1].kind != "NEWLINE":
        add("NEWLINE", "\n")
    add("EOF", None)
    return tokens
