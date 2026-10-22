"""Echo test suite. Run: cd python && python -m pytest -q"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from echo import run  # noqa: E402
from echo.lib import bio  # noqa: E402

EX = os.path.join(os.path.dirname(__file__), "..", "echo", "examples")


def out(code):
    return run(code)


# ---------------- language ----------------
def test_say_and_set():
    assert out('set x to 2\nsay x + 3') == "5"
    assert out('x = 2\nx *= 5\nsay x') == "10"
    assert out('set x to 1\nset x += 4\nsay x') == "5"


def test_text_interpolation():
    assert out('set n to "Reno"\nsay "Hi {n}, {1 + 1}"') == "Hi Reno, 2"
    assert out('say "brace \\{ok\\}"') == "brace {ok}"


def test_numbers():
    assert out('say 7 / 2, 6 / 2, 2 ^ 10, 10 % 3, 7 // 2') == "3.5 3 1024 1 3"
    assert out('say 0.1 + 0.2') == "0.3"


def test_if_else():
    code = 'for each n in [1, 5, 9]\n if n < 3 then\n  say "low"\n else if n < 7 then\n  say "mid"\n else\n  say "high"\n end\nend'
    assert out(code) == "low\nmid\nhigh"


def test_loops_break_continue():
    code = 'for i from 1 to 10\n if i == 3 then\n continue\n end\n if i == 6 then\n break\n end\n say i\nend'
    assert out(code) == "1\n2\n4\n5"
    assert out('repeat 3 times\n say "x"\nend') == "x\nx\nx"
    assert out('set n to 0\nwhile n < 3\n n += 1\nend\nsay n') == "3"
    assert out('for i from 10 to 1 step -3\n say i\nend') == "10\n7\n4\n1"
    assert out('for each k, v in {a: 1, b: 2}\n say k, v\nend') == "a 1\nb 2"


def test_functions_and_recursion():
    code = 'define fact(n)\n if n <= 1 then\n  return 1\n end\n return n * fact(n - 1)\nend\nsay fact(12)'
    assert out(code) == "479001600"
    assert out('define f(a, b = 10)\n return a + b\nend\nsay f(1), f(1, b: 2)') == "11 3"


def test_lambda_map_filter():
    assert out('say map([1, 2, 3], fn(x) -> x * x)') == "[1, 4, 9]"
    assert out('say filter(range(1, 10), fn(n) -> n % 3 == 0)') == "[3, 6, 9]"


def test_closures():
    code = 'define make_adder(n)\n return fn(x) -> x + n\nend\nset add5 to make_adder(5)\nsay add5(10)'
    assert out(code) == "15"


def test_records_and_maps():
    code = 'record Gene(name, seq = "")\nset g to Gene("gfp")\nsay g.name, type(g)\nset g.seq to "ATG"\nsay g'
    assert out(code) == 'gfp Gene\nGene(name: "gfp", seq: "ATG")'
    assert out('set m to {a: 1}\nset m["b"] to 2\nsay m, length(m)') == "{a: 1, b: 2} 2"


def test_try_fail():
    assert out('try\n fail "oops"\ncatch e\n say "got", e\nend') == "got oops"
    assert out('try\n say 1 / 0\ncatch e\n say e\nend') == "Can't divide by zero."


def test_scope_local_by_default():
    code = 'set x to 1\ndefine f()\n set x to 99\n return x\nend\nsay f(), x'
    assert out(code) == "99 1"
    code = 'set x to 1\ndefine f()\n global x\n set x to 99\nend\nf()\nsay x'
    assert out(code) == "99"


def test_of_and_method_style():
    assert out('say length of "ATGC"') == "4"
    assert out('say "atgc".upper()') == "ATGC"
    assert out('say "ATGC".reverse_complement()') == "GCAT"


def test_errors_are_friendly():
    assert "Did you mean 'gc'" in out('say gcc("ATG")')
    assert "Line 2" in out('set x to [1]\nsay x[3]')
    assert "has no 'end'" in out('if true then\n say 1\n')
    assert "Echo word" in out('set step to 1')


# ---------------- gates ----------------
def test_gates():
    assert out('say 1 and 0, 1 or 0, 1 xor 1, 1 nand 1, 0 nor 0, 1 xnor 1, not 1') == "0 1 0 0 1 1 0"
    assert out('say true xor false, not true') == "true false"
    assert "1 1 | 0" in out('say truth_table("xor")')
    assert out('say add_binary("1011", "0110")') == "10001"
    assert out('say half_adder(1, 1)') == "{sum: 0, carry: 1}"


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


# ---------------- cyber / ml ----------------
def test_cyber():
    assert out('say caesar("abc", 3)') == "def"
    assert out('say sha256("echo")') == "092c79e8f80e559e404bcf660c48f3522b67aba9ff1484b0367e1a4ddef7431d"
    assert out('say base64_decode(base64_encode("hi"))') == "hi"


def test_ml():
    assert out('set m to linear_fit([1, 2, 3], [2, 4, 6])\nsay m.slope, m.intercept') == "2 0"
    assert out('set m to train("linear", [[1, 1], [2, 1], [3, 2], [4, 3]], [3, 4, 7, 10])\nsay round(predict(m, [5, 3]))') == "11"
    assert out('say mean([1, 2, 3, 4]), median([3, 1, 2])') == "2.5 2"


def test_ai_without_key_is_friendly(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHO_HOME", str(tmp_path))
    monkeypatch.delenv("ECHO_AI_KEY", raising=False)
    assert "No AI key set" in out('say ai("hi")')


# ---------------- examples and converters ----------------
@pytest.mark.parametrize("name", ["hello", "bio", "gates", "cyber", "ml", "games"])
def test_examples_run(name):
    with open(os.path.join(EX, name + ".echo"), encoding="utf-8") as f:
        text = out(f.read())
    assert "Line " not in text


@pytest.mark.parametrize("name", ["hello", "bio", "gates", "games"])
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
@pytest.mark.parametrize("name", ["hello", "bio", "gates", "games"])
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
