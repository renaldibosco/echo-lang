"""Echo error types. Every error carries a line number and a friendly message."""


class EchoError(Exception):
    def __init__(self, message, line=None, hint=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.hint = hint

    def __str__(self):
        text = self.message
        if self.line:
            text = "Line %d: %s" % (self.line, text)
        if self.hint:
            text += "\n  Hint: " + self.hint
        return text


class EchoSyntaxError(EchoError):
    pass


class EchoRuntimeError(EchoError):
    pass


class EchoStopped(Exception):
    """Raised when the user presses Stop."""
