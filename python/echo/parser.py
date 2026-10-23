"""Builds an Echo syntax tree from tokens (Echo 2 grammar, see docs/LANGUAGE.md)."""
from .errors import EchoSyntaxError
from .lexer import tokenize


class Node:
    """A syntax tree node. `kind` names the node, other fields are attributes."""

    def __init__(self, kind, line, **fields):
        self.kind = kind
        self.line = line
        self.__dict__.update(fields)

    def __repr__(self):
        items = ", ".join("%s=%r" % (k, v) for k, v in self.__dict__.items() if k not in ("kind", "line"))
        return "%s(%s)" % (self.kind, items)


class TypeSpec:
    """A type written in code: `number`, `list of dna`, `text or nothing`."""

    def __init__(self, name, of=None, optional=False, line=None):
        self.name = name
        self.of = of
        self.optional = optional
        self.line = line

    def __str__(self):
        text = self.name + (" of " + str(self.of) if self.of else "")
        return text + (" or nothing" if self.optional else "")

    __repr__ = __str__


OR_OPS = {"or", "nor", "xor", "xnor"}
AND_OPS = {"and", "nand"}
COMPARE_OPS = {"==", "!=", "<", ">", "<=", ">="}
OLD_ASSIGN = {"=", "+=", "-=", "*=", "/="}
REMOVED_STATEMENTS = {
    "stop": "Write: break",
    "skip": "Write: continue",
    "pass": "Leave the block empty instead.",
}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.loop_depth = 0
        self.func_depth = 0

    # ---- helpers ----
    @property
    def tok(self):
        return self.tokens[self.pos]

    def peek(self, k=1):
        return self.tokens[min(self.pos + k, len(self.tokens) - 1)]

    def at(self, kind, value=None):
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def at_kw(self, *words):
        return self.tok.kind == "KEYWORD" and self.tok.value in words

    def at_op(self, *ops):
        return self.tok.kind == "OP" and self.tok.value in ops

    def at_name(self, word):
        return self.tok.kind == "NAME" and self.tok.value == word

    def advance(self):
        t = self.tok
        self.pos += 1
        return t

    def fail(self, message, line=None, hint=None, code=None):
        raise EchoSyntaxError(message, line or self.tok.line, hint, code)

    def expect_kw(self, word, hint=None):
        if not self.at_kw(word):
            self.fail("Expected '%s' but found %s." % (word, self.describe()), hint=hint)
        return self.advance()

    def expect_op(self, op, hint=None):
        if not self.at_op(op):
            self.fail("Expected '%s' but found %s." % (op, self.describe()), hint=hint)
        return self.advance()

    def expect_name(self, what="a name"):
        if self.tok.kind != "NAME":
            if self.tok.kind == "KEYWORD":
                self.fail("'%s' is an Echo keyword and can't be used as %s." % (self.tok.value, what),
                          hint="Choose another name, e.g. %s_value." % self.tok.value, code="E105")
            self.fail("Expected %s but found %s." % (what, self.describe()))
        return self.advance().value

    def describe(self):
        t = self.tok
        if t.kind == "EOF":
            return "the end of the program"
        if t.kind == "NEWLINE":
            return "the end of the line"
        if t.kind == "STRING":
            return "some text"
        return "'%s'" % (t.value,)

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.advance()

    def end_of_statement(self):
        if self.at("NEWLINE"):
            self.advance()
            return
        if self.at("EOF"):
            return
        if self.at_op(*OLD_ASSIGN):
            self.old_assign()
        if self.at_kw("is"):
            self.old_is()
        if self.at_name("of"):
            self.old_of()
        self.fail("Unexpected %s." % self.describe(), hint="Put each statement on its own line.")

    # ---- Echo 1 forms with clear messages ----
    def old_assign(self, target="x"):
        op = self.tok.value
        if op == "=":
            self.fail("'=' is not used to set variables in Echo 2.", hint="Write: set %s to value" % target,
                      code="E104")
        self.fail("'%s' was removed in Echo 2." % op,
                  hint="Write: set %s to %s %s value" % (target, target, op[0]), code="E104")

    def old_is(self):
        self.fail("'is' was removed in Echo 2.", hint="Compare with == or != (e.g. if x == 3 then).", code="E104")

    def old_of(self):
        self.fail("'name of value' calls were removed in Echo 2.", hint="Call functions with brackets: length(seq)",
                  code="E104")

    # ---- program and blocks ----
    def parse_program(self):
        body = []
        self.skip_newlines()
        while not self.at("EOF"):
            body.append(self.statement())
            self.skip_newlines()
        return Node("Program", 1, body=body)

    def block(self, stops, opener, line):
        body = []
        self.skip_newlines()
        while not (self.tok.kind == "KEYWORD" and self.tok.value in stops):
            if self.at("EOF"):
                self.fail("The '%s' block that starts on line %d has no 'end'." % (opener, line), line,
                          "Close it with end.", code="E102")
            body.append(self.statement())
            self.skip_newlines()
        return body

    def finish_end(self):
        self.expect_kw("end")
        if self.tok.kind == "KEYWORD" and self.tok.value in ("if", "repeat", "while", "for", "define", "try"):
            self.fail("'end %s' was removed in Echo 2." % self.tok.value, hint="Write just: end", code="E104")
        self.end_of_statement()

    def loop_body(self, opener, line):
        self.loop_depth += 1
        try:
            return self.block({"end"}, opener, line)
        finally:
            self.loop_depth -= 1

    # ---- statements ----
    def statement(self):
        t = self.tok
        line = t.line
        if t.kind == "KEYWORD":
            method = getattr(self, "st_" + t.value, None)
            if method:
                return method()
        if t.kind == "NAME" and t.value in REMOVED_STATEMENTS and self.peek().kind in ("NEWLINE", "EOF"):
            self.fail("'%s' was removed in Echo 2." % t.value, hint=REMOVED_STATEMENTS[t.value], code="E104")
        expr = self.expression()
        if self.at_op(*OLD_ASSIGN):
            self.old_assign(expr.name if expr.kind == "Name" else "x")
        self.end_of_statement()
        return Node("ExprStmt", line, expr=expr)

    def check_target(self, expr):
        if expr.kind not in ("Name", "Index", "Attr"):
            self.fail("Only a name, a list item or a field can be set.", expr.line, code="E106")

    def type_spec(self, nested=False):
        line = self.tok.line
        if self.at_kw("nothing"):
            self.advance()
            return TypeSpec("nothing", line=line)
        if self.tok.kind != "NAME":
            self.fail("Expected a type (like number, text, list of dna) but found %s." % self.describe(),
                      code="E304")
        name = self.advance().value
        of = None
        if self.at_name("of"):
            self.advance()
            of = self.type_spec(nested=True)
        spec = TypeSpec(name, of, line=line)
        if not nested and self.at_kw("or"):
            self.advance()
            self.expect_kw("nothing", "Only 'or nothing' can follow a type, e.g. text or nothing.")
            spec.optional = True
        return spec

    def st_set(self):
        line = self.advance().line
        target = self.postfix()
        self.check_target(target)
        type_ = None
        if self.at_op(":"):
            if target.kind != "Name":
                self.fail("Only plain variables can have a type.", hint="Give record fields their type in the record.")
            self.advance()
            type_ = self.type_spec()
        if self.at_op(*OLD_ASSIGN):
            name = target.name if target.kind == "Name" else "x"
            if self.tok.value == "=":
                self.fail("Use 'to' after set.", hint="Write: set %s to value" % name, code="E104")
            self.old_assign(name)
        self.expect_kw("to", "Write: set name to value")
        value = self.expression()
        self.end_of_statement()
        return Node("Set", line, target=target, value=value, type=type_)

    def st_add(self):
        line = self.advance().line
        value = self.expression()
        self.expect_kw("to", "Write: add item to list")
        target = self.postfix()
        self.end_of_statement()
        return Node("Add", line, value=value, target=target)

    def st_say(self):
        line = self.advance().line
        values = []
        if not self.at("NEWLINE") and not self.at("EOF"):
            values.append(self.expression())
            while self.at_op(","):
                self.advance()
                values.append(self.expression())
        self.end_of_statement()
        return Node("Say", line, values=values)

    def st_ask(self):
        line = self.advance().line
        if self.at_name("ai"):
            self.fail("'ask ai' was removed in Echo 2.", hint='Write: set answer to ai.ask("your question")',
                      code="E104")
        prompt = self.expression()
        if not self.at_kw("into"):
            self.fail("Expected 'into' after the question.", line, 'Write: ask "Your name?" into name')
        self.advance()
        name = self.expect_name("a name to store the answer")
        self.end_of_statement()
        return Node("Ask", line, prompt=prompt, name=name)

    def condition(self, word):
        cond = self.expression()
        if not self.at_kw("then"):
            if self.at_kw("is"):
                self.old_is()
            self.fail("Expected 'then' after the %s condition." % word, hint="Write: %s x > 3 then" % word)
        self.advance()
        return cond

    def st_if(self):
        line = self.advance().line
        branches = [(self.condition("if"), self.block({"else", "end"}, "if", line))]
        else_body = None
        while self.at_kw("else"):
            eline = self.advance().line
            if self.at_kw("if"):
                self.advance()
                c = self.condition("else if")
                branches.append((c, self.block({"else", "end"}, "else if", eline)))
            else:
                else_body = self.block({"end"}, "else", eline)
                break
        self.finish_end()
        return Node("If", line, branches=branches, else_body=else_body)

    def st_repeat(self):
        line = self.advance().line
        if self.at_name("forever"):
            self.fail("'repeat forever' was removed in Echo 2.", hint="Write: while true", code="E104")
        count = self.expression()
        self.expect_kw("times", "Write: repeat 5 times")
        body = self.loop_body("repeat", line)
        self.finish_end()
        return Node("Repeat", line, count=count, body=body)

    def st_while(self):
        line = self.advance().line
        cond = self.expression()
        if self.at_kw("then"):
            self.fail("'while' does not use 'then'.", hint="Write: while count > 0")
        body = self.loop_body("while", line)
        self.finish_end()
        return Node("While", line, cond=cond, body=body)

    def st_for(self):
        line = self.advance().line
        if self.at_kw("each"):
            self.advance()
            var = self.expect_name("a loop name")
            var2 = None
            if self.at_op(","):
                self.advance()
                var2 = self.expect_name("a second loop name")
            self.expect_kw("in", "Write: for each item in list")
            iterable = self.expression()
            body = self.loop_body("for", line)
            self.finish_end()
            return Node("ForEach", line, var=var, var2=var2, iterable=iterable, body=body)
        var = self.expect_name("a loop name")
        if self.at_kw("in") or self.at_op(","):
            self.fail("Loops over items need 'each'.", hint="Write: for each %s in ..." % var, code="E104")
        self.expect_kw("from", "Write: for i from 1 to 10   or   for each item in list")
        start = self.expression()
        self.expect_kw("to")
        stop = self.expression()
        step = None
        if self.at_kw("step"):
            self.advance()
            step = self.expression()
        body = self.loop_body("for", line)
        self.finish_end()
        return Node("ForRange", line, var=var, start=start, stop=stop, step=step, body=body)

    def _simple(self, kind, word):
        line = self.advance().line
        if self.loop_depth == 0:
            self.fail("'%s' can only be used inside a loop." % word, line, code="E107")
        self.end_of_statement()
        return Node(kind, line)

    def st_break(self):
        return self._simple("Break", "break")

    def st_continue(self):
        return self._simple("Continue", "continue")

    def params(self, what="parameter"):
        params = []
        self.expect_op("(", "Write the %ss in brackets, e.g. (seq, salt = 50)." % what)
        self.skip_newlines()
        seen_default = False
        while not self.at_op(")"):
            pline = self.tok.line
            name = self.expect_name("a %s name" % what)
            type_ = None
            if self.at_op(":"):
                self.advance()
                type_ = self.type_spec()
            default = None
            if self.at_op("="):
                self.advance()
                default = self.expression()
                seen_default = True
            elif seen_default:
                self.fail("'%s' needs a default value because an earlier %s has one." % (name, what), pline)
            if any(p[0] == name for p in params):
                self.fail("The %s '%s' is listed twice." % (what, name), pline)
            params.append((name, default, type_))
            self.skip_newlines()
            if not self.at_op(")"):
                self.expect_op(",")
                self.skip_newlines()
        self.advance()
        return params

    def st_define(self):
        line = self.advance().line
        name = self.expect_name("a function name")
        params = self.params()
        returns = None
        if self.at_op("->"):
            self.advance()
            returns = self.type_spec()
        saved_loop = self.loop_depth
        self.loop_depth = 0
        self.func_depth += 1
        try:
            body = self.block({"end"}, "define", line)
        finally:
            self.loop_depth = saved_loop
            self.func_depth -= 1
        self.finish_end()
        return Node("Define", line, name=name, params=params, returns=returns, body=body)

    def st_return(self):
        line = self.advance().line
        if self.func_depth == 0:
            self.fail("'return' can only be used inside a function.", line, code="E107")
        value = None
        if not self.at("NEWLINE") and not self.at("EOF"):
            value = self.expression()
        self.end_of_statement()
        return Node("Return", line, value=value)

    def st_try(self):
        line = self.advance().line
        body = self.block({"catch", "end"}, "try", line)
        err, handler = None, []
        if self.at_kw("catch"):
            cline = self.advance().line
            if self.tok.kind == "NAME":
                err = self.advance().value
            handler = self.block({"end"}, "catch", cline)
        self.finish_end()
        return Node("Try", line, body=body, err=err, handler=handler)

    def st_fail(self):
        line = self.advance().line
        value = self.expression()
        self.end_of_statement()
        return Node("Fail", line, value=value)

    def st_use(self):
        line = self.advance().line
        if not self.at("STRING"):
            if self.tok.kind == "NAME":
                self.fail("Built-in modules don't need 'use'.",
                          hint="Just write %s.function(...). 'use' is for your own .echo files." % self.tok.value,
                          code="E104")
            self.fail("Expected a file name in quotes.", hint='Write: use "helpers.echo"')
        parts = self.advance().value
        path = "".join(p[1] for p in parts if p[0] == "text")
        alias = None
        if self.at_kw("as"):
            self.advance()
            alias = self.expect_name("a module name")
        self.end_of_statement()
        return Node("Use", line, path=path, alias=alias)

    def st_record(self):
        line = self.advance().line
        name = self.expect_name("a record name")
        if not name[0].isupper():
            self.fail("Record names start with a capital letter.", line,
                      "Write: record %s(...)" % (name[0].upper() + name[1:]))
        fields = self.params("field")
        self.end_of_statement()
        return Node("Record", line, name=name, fields=fields)

    def st_global(self):
        line = self.advance().line
        names = [self.expect_name()]
        while self.at_op(","):
            self.advance()
            names.append(self.expect_name())
        self.end_of_statement()
        return Node("Global", line, names=names)

    # ---- expressions ----
    def expression(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.at_kw(*OR_OPS):
            t = self.advance()
            left = Node("Logic", t.line, op=t.value, left=left, right=self.and_expr())
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.at_kw(*AND_OPS):
            t = self.advance()
            left = Node("Logic", t.line, op=t.value, left=left, right=self.not_expr())
        return left

    def not_expr(self):
        if self.at_kw("not"):
            t = self.advance()
            return Node("Not", t.line, expr=self.not_expr())
        return self.comparison()

    def comparison(self):
        left = self.additive()
        while True:
            t = self.tok
            if self.at_op(*COMPARE_OPS):
                op = self.advance().value
            elif self.at_kw("in"):
                self.advance()
                op = "in"
            elif self.at_kw("not") and self.peek().kind == "KEYWORD" and self.peek().value == "in":
                self.advance()
                self.advance()
                op = "not in"
            elif self.at_kw("is"):
                self.old_is()
            else:
                return left
            left = Node("Compare", t.line, op=op, left=left, right=self.additive())

    def additive(self):
        left = self.term()
        while self.at_op("+", "-"):
            t = self.advance()
            left = Node("BinOp", t.line, op=t.value, left=left, right=self.term())
        return left

    def term(self):
        left = self.unary()
        while self.at_op("*", "/", "%", "//"):
            t = self.advance()
            left = Node("BinOp", t.line, op=t.value, left=left, right=self.unary())
        return left

    def unary(self):
        if self.at_op("-"):
            t = self.advance()
            return Node("Neg", t.line, expr=self.unary())
        return self.power()

    def power(self):
        base = self.postfix()
        if self.at_op("^"):
            t = self.advance()
            return Node("BinOp", t.line, op="^", left=base, right=self.unary())
        return base

    def postfix(self):
        expr = self.primary()
        while True:
            if self.at_op("("):
                expr = self.call(expr)
            elif self.at_op("["):
                line = self.advance().line
                start = None if self.at_op(":") else self.expression()
                if self.at_op(":"):
                    self.advance()
                    stop = None if self.at_op("]") else self.expression()
                    self.expect_op("]")
                    expr = Node("Slice", line, obj=expr, start=start, stop=stop)
                else:
                    self.expect_op("]")
                    expr = Node("Index", line, obj=expr, index=start)
            elif self.at_op("."):
                line = self.advance().line
                if self.tok.kind not in ("NAME", "KEYWORD"):
                    self.fail("Expected a name after '.'.", line)
                expr = Node("Attr", line, obj=expr, name=self.advance().value)
            elif expr.kind == "Name" and self.at_name("of"):
                self.old_of()
            else:
                return expr

    def call(self, func):
        line = self.advance().line
        args, kwargs = [], []
        self.skip_newlines()
        while not self.at_op(")"):
            if self.tok.kind == "NAME" and self.peek().kind == "OP" and self.peek().value == ":":
                key = self.advance().value
                self.advance()
                if any(k == key for k, _ in kwargs):
                    self.fail("The setting '%s' is given twice." % key)
                kwargs.append((key, self.expression()))
            else:
                if kwargs:
                    self.fail("Put named values after the normal ones.", hint="f(1, 2, size: 3)")
                args.append(self.expression())
            self.skip_newlines()
            if not self.at_op(")"):
                self.expect_op(",", "Separate values with commas.")
                self.skip_newlines()
        self.advance()
        return Node("Call", line, func=func, args=args, kwargs=kwargs)

    def primary(self):
        t = self.tok
        line = t.line
        if t.kind == "NUMBER":
            self.advance()
            return Node("Num", line, value=t.value)
        if t.kind == "STRING":
            self.advance()
            parts = []
            for p in t.value:
                if p[0] == "text":
                    parts.append(p[1])
                else:
                    sub = Parser(tokenize(p[1]))
                    for tk in sub.tokens:
                        tk.line = p[2]
                    e = sub.expression()
                    if not sub.at("NEWLINE") and not sub.at("EOF"):
                        self.fail("Bad expression inside {} in text.", line)
                    parts.append(e)
            return Node("Str", line, parts=parts)
        if t.kind == "NAME":
            self.advance()
            return Node("Name", line, name=t.value)
        if t.kind == "KEYWORD":
            if t.value in ("true", "false"):
                self.advance()
                return Node("Bool", line, value=t.value == "true")
            if t.value == "nothing":
                self.advance()
                return Node("Nothing", line)
            if t.value == "fn":
                self.advance()
                params = self.params()
                self.expect_op("->", "Write: fn(x) -> x * 2")
                return Node("Lambda", line, params=params, body=self.expression())
        if self.at_op("("):
            self.advance()
            self.skip_newlines()
            e = self.expression()
            self.skip_newlines()
            self.expect_op(")")
            return e
        if self.at_op("["):
            self.advance()
            items = []
            self.skip_newlines()
            while not self.at_op("]"):
                items.append(self.expression())
                self.skip_newlines()
                if not self.at_op("]"):
                    self.expect_op(",")
                    self.skip_newlines()
            self.advance()
            return Node("List", line, items=items)
        if self.at_op("{"):
            self.advance()
            pairs = []
            self.skip_newlines()
            while not self.at_op("}"):
                if self.tok.kind == "NAME" and self.peek().kind == "OP" and self.peek().value == ":":
                    key = Node("Str", self.tok.line, parts=[self.advance().value])
                else:
                    key = self.expression()
                self.expect_op(":")
                pairs.append((key, self.expression()))
                self.skip_newlines()
                if not self.at_op("}"):
                    self.expect_op(",")
                    self.skip_newlines()
            self.advance()
            return Node("Map", line, pairs=pairs)
        if t.kind == "KEYWORD":
            if t.value == "is":
                self.old_is()
            self.fail("'%s' can't be used here." % t.value, line,
                      "'%s' is an Echo keyword, so it can't be a name." % t.value, code="E105")
        self.fail("Expected a value but found %s." % self.describe(), line)


def parse(source):
    return Parser(tokenize(source)).parse_program()
