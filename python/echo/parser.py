"""Builds an Echo syntax tree from tokens."""
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


BLOCK_ENDS = {"end"}
END_WORDS = {"if", "repeat", "while", "for", "define", "try", "record"}
OR_OPS = {"or", "nor", "xor", "xnor"}
AND_OPS = {"and", "nand"}
COMPARE_OPS = {"==", "!=", "<", ">", "<=", ">="}
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/="}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

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

    def advance(self):
        t = self.tok
        self.pos += 1
        return t

    def expect_kw(self, word, hint=None):
        if not self.at_kw(word):
            raise EchoSyntaxError("Expected '%s' but found %s." % (word, self.describe()), self.tok.line, hint)
        return self.advance()

    def expect_op(self, op, hint=None):
        if not self.at_op(op):
            raise EchoSyntaxError("Expected '%s' but found %s." % (op, self.describe()), self.tok.line, hint)
        return self.advance()

    def expect_name(self, what="a name"):
        if self.tok.kind != "NAME":
            hint = None
            if self.tok.kind == "KEYWORD":
                hint = "'%s' is an Echo word and can't be used as a name." % self.tok.value
            raise EchoSyntaxError("Expected %s but found %s." % (what, self.describe()), self.tok.line, hint)
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
        elif not self.at("EOF"):
            raise EchoSyntaxError("I didn't expect %s here." % self.describe(), self.tok.line,
                                  "Put each statement on its own line.")

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
                raise EchoSyntaxError("The '%s' block that starts on line %d has no 'end'." % (opener, line), line)
            body.append(self.statement())
            self.skip_newlines()
        return body

    def finish_end(self):
        self.expect_kw("end")
        if self.tok.kind == "KEYWORD" and self.tok.value in END_WORDS:
            self.advance()
        self.end_of_statement()

    # ---- statements ----
    def statement(self):
        t = self.tok
        line = t.line
        if t.kind == "KEYWORD":
            w = t.value
            method = getattr(self, "st_" + w, None)
            if method:
                return method()
        expr = self.expression()
        if self.at_op(*ASSIGN_OPS):
            op = self.advance().value
            self.check_target(expr)
            value = self.expression()
            self.end_of_statement()
            return Node("Set", line, target=expr, value=value, op=op)
        self.end_of_statement()
        return Node("ExprStmt", line, expr=expr)

    def check_target(self, expr):
        if expr.kind not in ("Name", "Index", "Attr"):
            raise EchoSyntaxError("You can only set a name, a list item or a field.", expr.line)

    def st_set(self):
        line = self.advance().line
        target = self.postfix()
        self.check_target(target)
        op = "="
        if self.at_op(*ASSIGN_OPS):
            op = self.advance().value
        else:
            self.expect_kw("to", "Write: set name to value")
        value = self.expression()
        self.end_of_statement()
        return Node("Set", line, target=target, value=value, op=op)

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
        ai = False
        if self.tok.kind == "NAME" and self.tok.value == "ai":
            self.advance()
            ai = True
        prompt = self.expression()
        name = None
        if self.at_kw("into"):
            self.advance()
            name = self.expect_name("a name to store the answer")
        elif not ai:
            raise EchoSyntaxError("Expected 'into' after ask.", line, 'Write: ask "Your name?" into name')
        self.end_of_statement()
        return Node("Ask", line, prompt=prompt, name=name, ai=ai)

    def st_if(self):
        line = self.advance().line
        branches = []
        cond = self.expression()
        if self.at_kw("then"):
            self.advance()
        body = self.block({"else", "end"}, "if", line)
        branches.append((cond, body))
        else_body = None
        while self.at_kw("else"):
            eline = self.advance().line
            if self.at_kw("if"):
                self.advance()
                c = self.expression()
                if self.at_kw("then"):
                    self.advance()
                b = self.block({"else", "end"}, "else if", eline)
                branches.append((c, b))
            else:
                else_body = self.block({"end"}, "else", eline)
                break
        self.finish_end()
        return Node("If", line, branches=branches, else_body=else_body)

    def st_repeat(self):
        line = self.advance().line
        if self.tok.kind == "NAME" and self.tok.value == "forever":
            self.advance()
            body = self.block(BLOCK_ENDS, "repeat", line)
            self.finish_end()
            return Node("While", line, cond=Node("Bool", line, value=True), body=body)
        count = self.expression()
        self.expect_kw("times", "Write: repeat 5 times")
        body = self.block(BLOCK_ENDS, "repeat", line)
        self.finish_end()
        return Node("Repeat", line, count=count, body=body)

    def st_while(self):
        line = self.advance().line
        cond = self.expression()
        body = self.block(BLOCK_ENDS, "while", line)
        self.finish_end()
        return Node("While", line, cond=cond, body=body)

    def st_for(self):
        line = self.advance().line
        if self.at_kw("each"):
            self.advance()
        var = self.expect_name("a loop name")
        if self.at_kw("from"):
            self.advance()
            start = self.expression()
            self.expect_kw("to")
            stop = self.expression()
            step = None
            if self.at_kw("step"):
                self.advance()
                step = self.expression()
            body = self.block(BLOCK_ENDS, "for", line)
            self.finish_end()
            return Node("ForRange", line, var=var, start=start, stop=stop, step=step, body=body)
        var2 = None
        if self.at_op(","):
            self.advance()
            var2 = self.expect_name("a second loop name")
        self.expect_kw("in", "Write: for each item in list   or   for i from 1 to 10")
        iterable = self.expression()
        body = self.block(BLOCK_ENDS, "for", line)
        self.finish_end()
        return Node("ForEach", line, var=var, var2=var2, iterable=iterable, body=body)

    def _simple(self, kind):
        line = self.advance().line
        self.end_of_statement()
        return Node(kind, line)

    def st_break(self):
        return self._simple("Break")

    def st_stop(self):
        return self._simple("Break")

    def st_continue(self):
        return self._simple("Continue")

    def st_skip(self):
        return self._simple("Continue")

    def st_pass(self):
        return self._simple("Pass")

    def params(self):
        params = []
        if self.at_op("("):
            self.advance()
            while not self.at_op(")"):
                name = self.expect_name("a parameter name")
                default = None
                if self.at_op("="):
                    self.advance()
                    default = self.expression()
                params.append((name, default))
                if not self.at_op(")"):
                    self.expect_op(",")
            self.advance()
        return params

    def st_define(self):
        line = self.advance().line
        name = self.expect_name("a function name")
        params = self.params()
        body = self.block(BLOCK_ENDS, "define", line)
        self.finish_end()
        return Node("Define", line, name=name, params=params, body=body)

    def st_return(self):
        line = self.advance().line
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
            handler = self.block(BLOCK_ENDS, "catch", cline)
        self.finish_end()
        return Node("Try", line, body=body, err=err, handler=handler)

    def st_fail(self):
        line = self.advance().line
        value = self.expression()
        self.end_of_statement()
        return Node("Fail", line, value=value)

    def st_use(self):
        line = self.advance().line
        if self.at("STRING"):
            parts = self.advance().value
            path = "".join(p[1] for p in parts if p[0] == "text")
        else:
            path = self.expect_name("a file or library name")
        self.end_of_statement()
        return Node("Use", line, path=path)

    def st_record(self):
        line = self.advance().line
        name = self.expect_name("a record name")
        fields = [p for p in self.params()]
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
            elif self.at_kw("is"):
                self.advance()
                op = "=="
                if self.at_kw("not"):
                    self.advance()
                    op = "!="
            elif self.at_kw("in"):
                self.advance()
                op = "in"
            elif self.at_kw("not") and self.peek().kind == "KEYWORD" and self.peek().value == "in":
                self.advance()
                self.advance()
                op = "not in"
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
        if self.at_op("+"):
            self.advance()
            return self.unary()
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
                if self.at_op(":"):
                    start = None
                else:
                    start = self.expression()
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
                    raise EchoSyntaxError("Expected a field name after '.'.", line)
                expr = Node("Attr", line, obj=expr, name=self.advance().value)
            elif (expr.kind == "Name" and self.tok.kind == "NAME" and self.tok.value == "of"):
                line = self.advance().line
                arg = self.postfix()
                expr = Node("Call", line, func=expr, args=[arg], kwargs=[])
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
                kwargs.append((key, self.expression()))
            else:
                if kwargs:
                    raise EchoSyntaxError("Put named values after the normal ones.", self.tok.line)
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
                        raise EchoSyntaxError("Bad expression inside {} in text.", line)
                    parts.append(e)
            return Node("Str", line, parts=parts)
        if t.kind == "NAME":
            self.advance()
            return Node("Name", line, name=t.value)
        if t.kind == "KEYWORD":
            if t.value in ("true", "yes"):
                self.advance()
                return Node("Bool", line, value=True)
            if t.value in ("false", "no"):
                self.advance()
                return Node("Bool", line, value=False)
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
            raise EchoSyntaxError("'%s' can't be used here." % t.value, line,
                                  "'%s' is an Echo word, so it can't be a name. Try another name." % t.value)
        raise EchoSyntaxError("Expected a value but found %s." % self.describe(), line)


def parse(source):
    return Parser(tokenize(source)).parse_program()
