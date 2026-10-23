"""Echo test suite. Run: cd python && python -m pytest -q"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from echo import run, check_source, format_source  # noqa: E402
from echo.lib import bio  # noqa: E402
from echo.upgrade import upgrade_source  # noqa: E402

EX = os.path.join(os.path.dirname(__file__), "..", "echo", "examples")
EXAMPLES = ["hello", "control", "types", "bio", "gates", "cyber", "ml"]


def out(code):
    return run(code)


def code_of(text):
    """The error code in an error message, e.g. 'E201'."""
    return text.split("Error ", 1)[1].split()[0].rstrip(":") if "Error " in text else None


# ---------------- language ----------------
def test_say_and_set():
    assert out("set x to 2\nsay x + 3") == "5"
    assert out("set x to 2\nset x to x * 5\nsay x") == "10"


def test_text_interpolation():
    assert out('set n to "Ada"\nsay "Hi {n}, {1 + 1}"') == "Hi Ada, 2"
    assert out('say "brace \\{ok\\}"') == "brace {ok}"


def test_numbers():
    assert out("say 7 / 2, 6 / 2, 2 ^ 10, 10 % 3, 7 // 2") == "3.5 3 1024 1 3"
    assert out("say 0.1 + 0.2") == "0.3"


def test_if_else():
    code = ('for each n in [1, 5, 9]\n if n < 3 then\n  say "low"\n else if n < 7 then\n  say "mid"\n'
            ' else\n  say "high"\n end\nend')
    assert out(code) == "low\nmid\nhigh"


def test_loops_break_continue():
    code = "for i from 1 to 10\n if i == 3 then\n continue\n end\n if i == 6 then\n break\n end\n say i\nend"
    assert out(code) == "1\n2\n4\n5"
    assert out('repeat 3 times\n say "x"\nend') == "x\nx\nx"
    assert out("set n to 0\nwhile n < 3\n set n to n + 1\nend\nsay n") == "3"
    assert out("for i from 10 to 1 step -3\n say i\nend") == "10\n7\n4\n1"
    assert out("for each k, v in {a: 1, b: 2}\n say k, v\nend") == "a 1\nb 2"


def test_functions_and_recursion():
    code = "define fact(n)\n if n <= 1 then\n  return 1\n end\n return n * fact(n - 1)\nend\nsay fact(12)"
    assert out(code) == "479001600"
    assert out("define f(a, b = 10)\n return a + b\nend\nsay f(1), f(1, b: 2)") == "11 3"


def test_lambda_map_filter_closures():
    assert out("say map([1, 2, 3], fn(x) -> x * x)") == "[1, 4, 9]"
    assert out("say filter(range(1, 10), fn(n) -> n % 3 == 0)") == "[3, 6, 9]"
    code = "define make_adder(n)\n return fn(x) -> x + n\nend\nset add5 to make_adder(5)\nsay add5(10)"
    assert out(code) == "15"


def test_records_and_maps():
    code = 'record Gene(name, seq = "")\nset g to Gene("gfp")\nsay g.name, type(g)\nset g.seq to "ATG"\nsay g'
    assert out(code) == 'gfp Gene\nGene(name: "gfp", seq: "ATG")'
    assert out('set m to {a: 1}\nset m["b"] to 2\nsay m, length(m)') == "{a: 1, b: 2} 2"
    assert code_of(out('record Gene(name)\nset g to Gene("a")\nset g.size to 3')) == "E202"
    assert code_of(out("record Gene(name)\nset g to Gene()")) == "E205"


def test_try_fail_gives_error_record():
    assert out('try\n fail "oops"\ncatch e\n say e.code, e.message\nend') == "E407 oops"
    assert out("try\n say 1 / 0\ncatch e\n say e.code, e.message, e.line\nend") == "E401 Division by zero. 2"


def test_scope_local_by_default():
    code = "set x to 1\ndefine f()\n set x to 99\n return x\nend\nsay f(), x"
    assert out(code) == "99 1"
    code = "set x to 1\ndefine f()\n global x\n set x to 99\nend\nf()\nsay x"
    assert out(code) == "99"


def test_conditions_must_be_boolean():
    assert code_of(out("if 1 then\n say 1\nend")) == "E303"
    assert code_of(out('while "yes"\n say 1\nend')) == "E303"
    assert code_of(out("say filter([1, 2], fn(x) -> x)")) == "E303"
    assert code_of(out('say true and 1')) == "E301"


def test_in_is_exact():
    assert out('say "atg" in "ATGC", "ATG" in "ATGC"') == "false true"


# ---------------- one way to write each thing ----------------
@pytest.mark.parametrize("code", [
    "x = 5", "set x to 1\nx += 1", "set x to 1\nset x += 1", "set x to 1\nif x is 1 then\nend",
    'say length of "ab"', "for i from 1 to 2\n stop\nend", "repeat forever\nend", "say 1; say 2",
    "say 'hi'", 'ask ai "hi" into a', "use bio", "if true then\nend if", "for x in [1]\nend",
])
def test_echo1_forms_give_E104(code):
    assert code_of(out(code)) == "E104", out(code)


def test_old_names_point_to_new_ones():
    assert "bio.gc" in out('say gc("ATG")')
    assert "say" in out("print(1)")
    assert "uses true and false" in out("say yes")
    assert "upper(value)" in out('say "a".upper()')


def test_if_needs_then_and_parser_checks_placement():
    assert "then" in out("if true\n say 1\nend")
    assert code_of(out("break")) == "E107"
    assert code_of(out("return 1")) == "E107"
    assert code_of(out("set step to 1")) == "E105"
    assert "has no 'end'" in out("if true then\n say 1\n")


# ---------------- modules ----------------
def test_modules():
    assert out('say bio.gc("GGCC"), math.sqrt(16), math.round(2.567, 1), stats.mean([1, 2, 3])') == "100 4 2.6 2"
    assert out("random.seed(1)\nset a to random.integer(1, 100)\nrandom.seed(1)\nsay a == random.integer(1, 100)") \
        == "true"
    assert out("say type(bio), length(bio.stop_codons), math.pi > 3") == "module 3 true"
    assert code_of(out('say bio.gcc("A")')) == "E202"
    assert "Did you mean bio.gc" in out('say bio.gcc("A")')
    assert code_of(out("say bio()")) == "E206"


def test_use_file_as_module(tmp_path):
    (tmp_path / "helpers.echo").write_text("define twice(x)\n return x * 2\nend\nset version to 3\n")
    main = tmp_path / "main.echo"
    main.write_text('use "helpers.echo"\nuse "helpers.echo" as h\nsay helpers.twice(4), h.version\n')
    got = subprocess.run([sys.executable, "-m", "echo", str(main)], capture_output=True, text=True,
                         cwd=os.path.join(os.path.dirname(__file__), "..")).stdout.strip()
    assert got == "8 3"


def test_help_lists_modules():
    assert "bio" in out("help()") and "stats.mean" in out('help("stats")')
    assert "bio.gc(seq)" in out('help("bio.gc")')


# ---------------- types ----------------
def test_typed_variables():
    assert out("set n: number to 5\nset n to 6\nsay n") == "6"
    assert code_of(out('set n: number to 5\nset n to "six"')) == "E302"
    assert code_of(out('set s: dna to "ATGX"')) == "E302"
    assert out('set s: dna to "ATGN"\nsay s') == "ATGN"
    assert code_of(out("set xs: list of number to [1, \"a\"]")) == "E302"
    assert out("set t: text or nothing to nothing\nsay t") == "nothing"
    assert code_of(out("set t: integer to 2.5")) == "E302"
    assert code_of(out("set t: numbr to 2")) == "E304"


def test_typed_functions_and_records():
    f = "define half(x: number) -> number\n return x / 2\nend\n"
    assert out(f + "say half(5)") == "2.5"
    assert code_of(out(f + 'say half("5")')) == "E302"
    assert code_of(out('define f() -> number\n return "x"\nend\nsay f()')) == "E302"
    r = "record Primer(name: text, seq: dna, tm: number = 0)\n"
    assert out(r + 'say Primer("p", "ATG")') == 'Primer(name: "p", seq: "ATG", tm: 0)'
    assert code_of(out(r + 'say Primer("p", "AXG")')) == "E302"
    assert code_of(out(r + 'set p to Primer("p", "ATG")\nset p.tm to "hot"')) == "E302"


def test_type_of_values():
    assert out('say type(1), type("a"), type(true), type([]), type({}), type(nothing), type(fn(x) -> x)') == \
        "number text boolean list map nothing function"


# ---------------- error messages ----------------
def test_errors_have_codes_lines_and_hints():
    text = out('say gcc("ATG")')
    assert text.startswith("Error E201 at line 1:") and "Hint:" in text
    assert code_of(out("set x to [1]\nsay x[3]")) == "E402"
    assert "line 2" in out("set x to [1]\nsay x[3]")
    assert code_of(out("set m to {a: 1}\nsay m[\"b\"]")) == "E403"
    assert code_of(out("say 1 / 0")) == "E401"
    assert code_of(out('say "a" - 1')) == "E301"
    assert code_of(out("define f(a)\n return a\nend\nsay f(1, 2)")) == "E203"
    assert code_of(out("define f(a)\n return a\nend\nsay f(b: 1)")) == "E204"
    assert code_of(out("say math.sqrt()")) == "E203"
    assert code_of(out("define f(n)\n return f(n + 1)\nend\nsay f(1)")) == "E405"


def test_explain():
    from echo.errors import CODES, explain
    assert "Unknown name" in explain("E201")
    assert all(code[0] in "EW" and len(code) == 4 for code in CODES)


# ---------------- checker ----------------
def codes(src):
    return [d.code for d in check_source(src)]


def test_checker_finds_errors_without_running():
    assert codes('say lenght("a")') == ["E201"]
    assert codes('say bio.gcc("A")') == ["E202"]
    assert codes("define f(a, b = 1)\n return a\nend\nsay f()") == ["E205"]
    assert codes("define f(a)\n return a\nend\nsay f(1, 2)") == ["E203"]
    assert codes("define f(a)\n return a\nend\nsay f(1, c: 2)") == ["E204"]
    assert codes('set x: number to "a"') == ["E302"]
    assert codes("define f(x: number)\n return x\nend\nsay f(\"a\")") == ["E302"]
    assert codes("if 3 then\n say 1\nend") == ["E303"]
    assert codes("set x: numbr to 3") == ["E304"]
    assert codes("say math.sqrt(1, 2)") == ["E203"]
    assert codes('say "a" - 1') == ["E301"]
    assert codes("say 1 +") == ["E101"]


def test_checker_warnings():
    assert codes("define f()\n set unused to 1\n return 2\nend\nsay f()") == ["W101"]
    assert codes("define f()\n return 1\n say 2\nend\nsay f()") == ["W102"]
    assert codes("3 + 4") == ["W103"]
    assert codes("set length to 3") == ["W104"]
    assert codes("define f(x) -> number\n if x > 1 then\n  return 1\n end\nend\nsay f(1)") == ["W105"]


@pytest.mark.parametrize("name", EXAMPLES + ["ai"])
def test_examples_are_clean(name):
    with open(os.path.join(EX, name + ".echo"), encoding="utf-8") as f:
        src = f.read()
    assert check_source(src) == []
    assert format_source(src) == src


# ---------------- formatter ----------------
def test_formatter_layout():
    src = ('# demo\nset x to [1,2,\n  3]\ndefine f( a:number=2 ,b:text="x")->number\nreturn a*-1+ x[0:2][0]  # c\nend'
           '\n\n\n\nif x[0]>1 then\nsay "hi {x}",f(1)\nelse\nsay -3\nend\nsay math.sqrt( 4 )\n')
    want = ('# demo\nset x to [1, 2,\n    3]\ndefine f(a: number = 2, b: text = "x") -> number\n'
            '    return a * -1 + x[0:2][0]  # c\nend\n\nif x[0] > 1 then\n    say "hi {x}", f(1)\nelse\n'
            '    say -3\nend\nsay math.sqrt(4)\n')
    assert format_source(src) == want
    assert format_source(want) == want


def test_formatter_keeps_long_text():
    src = 'say """a\n   b  """\n'
    assert format_source(src) == src


# ---------------- upgrade from Echo 1 ----------------
ECHO1 = """x = 5
x += 2
set y += 1
if x is 7
  say gc of "GGCC"
end if
say "atgc".upper(), revcomp("ATG")
for n in [1, 2]
  if n is not 1 then
    stop
  end
end
ask ai 'hi' into answer
try
  say 1 / 0
catch problem
  say "got", problem
end
say "{mean([1, 3])}"
set ok to yes; say ok
"""


def test_upgrade_echo1():
    new, notes = upgrade_source(ECHO1)
    assert "set x to 5" in new and "set x to x + 2" in new and "set y to y + 1" in new
    assert "if x == 7 then" in new and "say bio.gc(\"GGCC\")" in new and "end if" not in new
    assert 'upper("atgc"), bio.reverse_complement("ATG")' in new
    assert "for each n in" in new and "n != 1" in new and "break" in new
    assert 'set answer to ai.ask("hi")' in new
    assert 'say "got", problem.message' in new
    assert '"{stats.mean([1, 3])}"' in new
    assert "set ok to true\nsay ok" in new
    assert [d for d in check_source(new) if d.is_error] == []


# ---------------- bio (checked against Biopython values) ----------------
GFP = ("ATGGCTAGCAAAGGAGAAGAACTTTTCACTGGAGTTGTCCCAATTCTTGTTGAATTAGATGGTGATGTTAATGGGCACAAATTTTCTGTCAGTGGAGAGGG"
       "TGAAGGTGATGCAACATACGGAAAACTTACCCTTAAATTTATTTGCACTACTGGAAAACTACCTGTTCCATGGCCAACACTTGTCACTACTTTCTCTTATG"
       "GTGTTCAATGCTTTTCAAGATACCCAGATCATATGAAACAGCATGACTTTTTCAAGAGTGCCATGCCCGAAGGTTATGTACAGGAAAGAACTATATTTTTC"
       "AAAGATGACGGGAACTACAAGACACGTGCTGAAGTCAAGTTTGAAGGTGATACCCTTGTTAATAGAATCGAGTTAAAAGGTATTGATTTTAAAGAAGATGG"
       "AAACATTCTTGGACACAAATTGGAATACAACTATAACTCACACAATGTATACATCATGGCAGACAAACAAAAGAATGGAATCAAAGTTAACTTCAAAATTA"
       "GACACAACATTGAAGATGGAAGCGTTCAACTAGCAGACCATTATCAACAAAATACTCCAATTGGCGATGGCCCTGTCCTTTTACCAGACAACCATTACCTG"
       "TCCACACAATCTGCCCTTTCGAAAGATCCCAACGAAAAGAGAGACCACATGGTCCTTCTTGAGTTTGTAACAGCTGCTGGGATTACACATGGCATGGATGA"
       "ACTATACAAATAA")


def test_bio_basics():
    assert bio.gc(GFP) == 38.75
    assert bio.revcomp("ATGC") == "GCAT"
    assert bio.translate("ATGGCCTAA") == "MA*"
    assert bio.translate(GFP, to_stop=True).startswith("MASKGEELFTGVVPILVELDGDVNGHKF")
    assert len(bio.find_orfs(GFP, 100)) == 1


def test_tm_matches_biopython():
    # values from Bio.SeqUtils.MeltingTemp.Tm_NN (defaults)
    assert abs(bio.tm_nn("TCAGTGGAGAGGGTGAAGGTGATGC") - 59.95) < 0.01
    assert abs(bio.tm_nn("CGAAAGGGCAGATTGTGTGGACAGG") - 60.01) < 0.01
    assert abs(bio.tm_nn("AGAGTTTGATCATGGCTCAG") - 49.36) < 0.01
    assert abs(bio.tm_nn("TCCGTAGGTGAACCTGCGG") - 55.87) < 0.01


def test_protein_matches_biopython():
    prot = bio.translate(GFP, to_stop=True)
    assert bio.protein_mass(prot) == 26957.0725
    assert bio.isoelectric_point(prot) == 5.67


def test_primers():
    p = bio.design_primers(GFP, 300, 700)
    assert p["product"] == 539 and p["problems"] == []
    assert 40 <= p["gc_forward"] <= 60 and 40 <= p["gc_reverse"] <= 60
    assert "no G/C clamp at the 3' end" in bio.primer_problems("ATATATATATATATATATTA")


def test_enzymes_and_align():
    assert bio.restriction_sites(GFP)["NcoI"] == [169]
    assert bio._digest(GFP, ["NcoI", "NdeI"]) == [487, 169, 64]
    assert bio._align("GATTACA", "GATTACA")["identity"] == 100


# ---------------- gates / cyber / ml ----------------
def test_gates():
    assert out("say 1 and 0, 1 or 0, 1 xor 1, 1 nand 1, 0 nor 0, 1 xnor 1, not 1") == "0 1 0 0 1 1 0"
    assert out("say true xor false, not true") == "true false"
    assert "1 1 | 0" in out('say gates.truth_table("xor")')
    assert out('say gates.add_binary("1011", "0110")') == "10001"
    assert out("say gates.half_adder(1, 1)") == "{sum: 0, carry: 1}"


def test_cyber():
    assert out('say cyber.caesar("abc", 3)') == "def"
    assert out('say cyber.sha256("echo")') == "092c79e8f80e559e404bcf660c48f3522b67aba9ff1484b0367e1a4ddef7431d"
    assert out('say cyber.base64_decode(cyber.base64_encode("hi"))') == "hi"


def test_ml():
    assert out("set m to stats.linear_fit([1, 2, 3], [2, 4, 6])\nsay m.slope, m.intercept") == "2 0"
    assert out('set m to ml.train("linear", [[1, 1], [2, 1], [3, 2], [4, 3]], [3, 4, 7, 10])\n'
               "say math.round(ml.predict(m, [5, 3]))") == "11"
    assert out("say stats.mean([1, 2, 3, 4]), stats.median([3, 1, 2])") == "2.5 2"


def test_ai_without_key_is_friendly(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHO_HOME", str(tmp_path))
    monkeypatch.delenv("ECHO_AI_KEY", raising=False)
    text = out('say ai.ask("hi")')
    assert code_of(text) == "E502" and "ai.setup" in text


# ---------------- examples and converters ----------------
@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_run(name):
    with open(os.path.join(EX, name + ".echo"), encoding="utf-8") as f:
        text = out(f.read())
    assert "Error E" not in text


SAME_OUTPUT = ["hello", "control", "types", "bio", "gates", "ml"]


@pytest.mark.parametrize("name", SAME_OUTPUT)
def test_python_converter_same_output(name, tmp_path):
    from echo.transpile.python import to_python
    with open(os.path.join(EX, name + ".echo"), encoding="utf-8") as f:
        src = f.read()
    py = tmp_path / "prog.py"
    py.write_text(to_python(src), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), ".."))
    got = subprocess.run([sys.executable, str(py)], capture_output=True, text=True, env=env).stdout.strip()
    assert got == out(src).strip()


@pytest.mark.skipif(shutil.which("javac") is None, reason="needs a JDK")
@pytest.mark.parametrize("name", ["hello", "control", "types", "bio", "gates"])
def test_java_converter_same_output(name, tmp_path):
    from echo.transpile.java import to_java
    with open(os.path.join(EX, name + ".echo"), encoding="utf-8") as f:
        src = f.read()
    rt = os.path.join(os.path.dirname(__file__), "..", "echo", "java", "echo", "EchoRuntime.java")
    (tmp_path / "echo").mkdir()
    shutil.copy(rt, tmp_path / "echo" / "EchoRuntime.java")
    cls = name.capitalize()
    (tmp_path / (cls + ".java")).write_text(to_java(src, cls), encoding="utf-8")
    subprocess.run(["javac", "-encoding", "UTF-8", "-d", "out", "echo/EchoRuntime.java", cls + ".java"],
                   cwd=tmp_path, check=True, capture_output=True)
    got = subprocess.run(["java", "-Dfile.encoding=UTF-8", "-cp", "out", cls], cwd=tmp_path,
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert got == out(src).strip()


def test_cli(tmp_path):
    f = tmp_path / "a.echo"
    f.write_text("set x to [1,2]\nsay x\n")
    cwd = os.path.join(os.path.dirname(__file__), "..")
    cli = [sys.executable, "-m", "echo"]
    r = subprocess.run(cli + ["fmt", "--check", str(f)], capture_output=True, text=True, cwd=cwd)
    assert r.returncode == 1
    subprocess.run(cli + ["fmt", str(f)], capture_output=True, text=True, cwd=cwd)
    assert f.read_text() == "set x to [1, 2]\nsay x\n"
    assert subprocess.run(cli + ["check", str(f)], capture_output=True, text=True, cwd=cwd).returncode == 0
    f.write_text("say nope\n")
    r = subprocess.run(cli + ["check", str(f)], capture_output=True, text=True, cwd=cwd)
    assert r.returncode == 1 and "E201" in r.stdout
    r = subprocess.run(cli + ["explain", "E303"], capture_output=True, text=True, cwd=cwd)
    assert "true/false" in r.stdout
