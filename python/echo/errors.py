"""Echo error types. Every error carries a code (like E201), a line number, a message and an optional hint.

Run `echolang explain E201` to read about any code.
"""

# code -> (title, explanation)
CODES = {
    # syntax
    "E101": ("Syntax error", "Echo could not read this line. Check the spelling of keywords and the order of words."),
    "E102": ("Block has no end", "Every if, while, for, repeat, define and try block must close with `end`."),
    "E103": ("Unclosed text or bracket", "A quote, (, [ or { was opened but never closed."),
    "E104": ("Echo 1 syntax",
             "This form was removed in Echo 2 so there is only one way to write each thing. "
             "The hint shows the Echo 2 form. `echolang upgrade FILE` rewrites old files for you."),
    "E105": ("Keyword used as a name", "Words such as set, to, if, end, step can't be variable or function names."),
    "E106": ("Can't set this", "Only a name, a list item (items[0]) or a field (sample.name) can be set."),
    "E107": ("Statement in the wrong place",
             "break and continue only work inside a loop; return only works inside a function."),
    # names
    "E201": ("Unknown name", "The name was never set or defined. Check the spelling, or set it first."),
    "E202": ("Unknown member", "The module, record or map has no member with this name."),
    "E203": ("Wrong number of values", "The function was called with too many or too few values."),
    "E204": ("Unknown setting", "The function has no named setting (keyword argument) with this name."),
    "E205": ("Missing value", "A required parameter was not given a value."),
    "E206": ("Not a function", "Only functions can be called with ( )."),
    # types
    "E301": ("Wrong type for operation", "The operator or function can't work with these kinds of values."),
    "E302": ("Type does not match",
             "A value does not match the declared type of a variable, parameter, return value or record field."),
    "E303": ("Condition is not true/false",
             "if, else if and while need a boolean (true or false). Compare explicitly, e.g. `if length(items) > 0 then`."),
    "E304": ("Unknown type", "The type name is not a built-in type or a record defined in the program."),
    # values
    "E401": ("Division by zero", "A number was divided by zero (/, // or %)."),
    "E402": ("Position out of range", "A list or text position is outside it. Positions start at 0."),
    "E403": ("Missing key", "The map has no such key. Use get(map, key, default) to read a key that may be missing."),
    "E404": ("Bad value", "A built-in function rejected this value. The message says why."),
    "E405": ("Too much recursion", "A function called itself too many times. Check its stop condition."),
    "E406": ("Stopped", "The program was stopped by the user."),
    "E407": ("Failure raised by the program", "The program ran a `fail` statement."),
    # outside world
    "E501": ("File problem", "A file could not be found, read or written."),
    "E502": ("AI problem", "The AI service is not set up or did not answer. Run ai.setup(provider, key) once."),
    # warnings (from `echolang check`)
    "W101": ("Unused variable", "A variable is set but never read."),
    "W102": ("Unreachable code", "Code after return, break, continue or fail never runs."),
    "W103": ("Unused value", "This line computes a value and throws it away. Did you mean `say` or `set`?"),
    "W104": ("Hides a built-in", "This name hides a built-in function or module of the same name."),
    "W105": ("Possible type mismatch", "The checker thinks this value has a different type than declared."),
}


class EchoError(Exception):
    default_code = "E101"

    def __init__(self, message, line=None, hint=None, code=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.hint = hint
        self.code = code or self.default_code

    def __str__(self):
        where = " at line %d" % self.line if self.line else ""
        text = "Error %s%s: %s" % (self.code, where, self.message)
        if self.hint:
            text += "\n  Hint: " + self.hint
        return text


class EchoSyntaxError(EchoError):
    default_code = "E101"


class EchoRuntimeError(EchoError):
    default_code = "E404"


class EchoTypeError(EchoRuntimeError):
    default_code = "E301"


class EchoStopped(Exception):
    """Raised when the user presses Stop."""


def explain(code):
    code = code.upper()
    if code not in CODES:
        return "Unknown code %s. Codes run from E101 to E502 and W101 to W105." % code
    title, text = CODES[code]
    return "%s  %s\n\n%s" % (code, title, text)
