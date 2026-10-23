"""Where every built-in lives in Echo 2.

A few everyday functions are global (length, text, range, sort, upper, ...). Everything else is reached through a
module: bio.gc(seq), math.sqrt(2), random.integer(1, 6), cyber.sha256(text), ai.ask(question).

The library files register functions under their internal names (the same names the Java runtime uses).
This file maps those internal names to the names Echo code writes.
"""
import re

from .values import Builtin, Module

MODULE_DOCS = {
    "math": "numbers: sqrt, round, floor, ceil, log, sin, pi, e",
    "random": "random numbers, choices and shuffling",
    "file": "read and write files on this device",
    "json": "turn JSON text into values and back",
    "time": "date, time and waiting",
    "bio": "DNA, RNA, proteins, primers, PCR, enzymes, gels, FASTA, lab maths",
    "gates": "logic gates, truth tables, adders, binary and bits",
    "cyber": "hashes, encodings, classic ciphers, password checks",
    "stats": "mean, median, standard deviation, correlation, straight-line fits",
    "ml": "small machine-learning models: linear, logistic, kNN, k-means",
    "ai": "ask Claude, Gemini or an OpenAI-compatible AI (your own key)",
}

# internal name -> (module, Echo name). Not listed: core functions stay global under their own name;
# bio/gates/cyber functions go to the module of the same name under their own name.
LAYOUT = {
    # math
    "abs": ("math", "abs"), "round": ("math", "round"), "floor": ("math", "floor"), "ceil": ("math", "ceil"),
    "sqrt": ("math", "sqrt"), "sin": ("math", "sin"), "cos": ("math", "cos"), "tan": ("math", "tan"),
    "exp": ("math", "exp"), "log": ("math", "log"), "log10": ("math", "log10"),
    "pi": ("math", "pi"), "e": ("math", "e"),
    # random
    "random": ("random", "number"), "random_int": ("random", "integer"), "choose": ("random", "choose"),
    "shuffle": ("random", "shuffle"), "seed": ("random", "seed"),
    # file / json / time
    "read_file": ("file", "read"), "write_file": ("file", "write"), "append_file": ("file", "append"),
    "file_exists": ("file", "exists"), "read_csv": ("file", "read_csv"),
    "from_json": ("json", "parse"), "to_json": ("json", "format"),
    "now": ("time", "now"), "today": ("time", "today"), "clock": ("time", "clock"), "wait": ("time", "wait"),
    # global renames
    "int": (None, "integer"), "bool": (None, "boolean"),
    # statistics and machine learning
    "mean": ("stats", "mean"), "median": ("stats", "median"), "mode": ("stats", "mode"),
    "variance": ("stats", "variance"), "stdev": ("stats", "stdev"), "correlation": ("stats", "correlation"),
    "normalize": ("stats", "normalize"), "zscore": ("stats", "zscore"), "linear_fit": ("stats", "linear_fit"),
    "train": ("ml", "train"), "predict": ("ml", "predict"), "probability": ("ml", "probability"),
    "accuracy": ("ml", "accuracy"), "error": ("ml", "error"), "split_data": ("ml", "split_data"),
    "cluster": ("ml", "cluster"),
    # ai
    "ai": ("ai", "ask"), "ai_setup": ("ai", "setup"), "ai_status": ("ai", "status"),
    "ai_code": ("ai", "code"), "ai_explain": ("ai", "explain"),
}
CATEGORY_MODULE = {"core": None, "bio": "bio", "gates": "gates", "cyber": "cyber", "ml": "ml", "ai": "ai"}

GLOBALS = {}          # Echo name -> value
MODULES = {}          # module name -> Module
QUALNAME = {}         # internal name -> what Echo code writes ("bio.gc", "integer", "math.pi")
INTERNAL = {}         # what Echo code writes -> internal name


def _place(internal, category):
    if internal in LAYOUT:
        return LAYOUT[internal]
    return CATEGORY_MODULE.get(category), internal


def build():
    if MODULES:
        return
    from . import stdlib
    registry = stdlib.raw()
    from .lib import CATEGORIES
    category_of = {}
    for cat, items in CATEGORIES.items():
        for name, _ in items:
            category_of[name] = cat
    for internal, value in registry.items():
        module, name = _place(internal, category_of.get(internal, "core"))
        qual = "%s.%s" % (module, name) if module else name
        QUALNAME[internal] = qual
        INTERNAL[qual] = internal
    pattern = re.compile(r"(?<![\w.])(%s)\(" % "|".join(
        sorted((re.escape(n) for n in QUALNAME), key=len, reverse=True)))

    def fix_doc(doc):
        doc = pattern.sub(lambda m: QUALNAME[m.group(1)] + "(", doc or "")
        doc = re.sub(r"'([A-Za-z0-9][\w ]*)'", r'"\1"', doc)      # Echo 2 text uses double quotes
        return doc.replace("''", '""').replace("' '", '" "')

    members = {m: {} for m in MODULE_DOCS}
    for internal, value in registry.items():
        module, name = _place(internal, category_of.get(internal, "core"))
        if isinstance(value, Builtin):
            value = Builtin(value.name, value.fn, value.needs_interp, fix_doc(value.doc), QUALNAME[internal])
        if module:
            members[module][name] = value
        else:
            GLOBALS[name] = value
    for m, doc in MODULE_DOCS.items():
        MODULES[m] = Module(m, members[m], doc)


def lookup_qualified(text):
    """'bio.gc' or 'length' -> value, or None."""
    build()
    if "." in text:
        m, n = text.split(".", 1)
        mod = MODULES.get(m)
        return mod.members.get(n) if mod else None
    return GLOBALS.get(text)


def old_name_hint(name):
    """For Echo 1 code: 'gc' -> 'bio.gc', 'print' -> say. None if it was never a built-in."""
    build()
    if name in ("print", "input"):
        return "Echo 2 uses the statements say and ask instead of %s()." % name
    if name in ("yes", "no"):
        return "Echo 2 uses true and false."
    old_aliases = {"len": "length", "size": "length", "str": "text", "num": "number", "gc_content": "gc",
                   "at_content": "at", "count_bases": "base_counts", "revcomp": "reverse_complement",
                   "pi_of": "isoelectric_point", "push": "append", "sleep": "wait", "average": "mean",
                   "sd": "stdev"}
    internal = old_aliases.get(name, name)
    qual = QUALNAME.get(internal)
    if qual and qual != name:
        return "In Echo 2 this is %s." % qual
    return None
