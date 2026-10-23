# Echo

**An English-like programming language for biology** — with logic gates, cyber-security tools, statistics,
machine learning and AI built in. Write it on your laptop or phone, check it, format it, and convert it to
Java or Python.

```echo
set gene: dna to bio.read_fasta("gfp.fasta")[0].seq
say "GC content: {bio.gc(gene)}%"

set pair to bio.design_primers(gene, product_min: 300, product_max: 700)
say "Forward {pair.forward}  GC {pair.gc_forward}%  Tm {pair.tm_forward} °C"
say "Reverse {pair.reverse}  GC {pair.gc_reverse}%  Tm {pair.tm_reverse} °C"

if length(pair.problems) == 0 then
    say "Both primers pass every check."
end
```

## Echo 2

- **One way to write each thing.** `set x to 5`, `if ... then ... end`, `for each item in items`. Old forms
  stop with error E104 and show the new form.
- **Modules.** `bio`, `math`, `random`, `stats`, `ml`, `gates`, `cyber`, `file`, `json`, `time`, `ai` —
  `bio.gc(seq)`, `math.sqrt(2)`, `ai.ask(question)`. Your own files are modules too: `use "helpers.echo"`.
- **Optional types.** `set primer: dna to "ATG..."`, `define tm(seq: dna) -> number`,
  `record Primer(name: text, seq: dna)`. Types include `dna`, `rna` and `protein`.
- **Error codes.** `Error E302 at line 4: Variable 'primer' must be dna, but got text "ATGX".`
  `echolang explain E302` explains any code.
- **Tools.** `echolang check` (find mistakes without running), `echolang fmt` (standard layout),
  `echolang upgrade` (convert Echo 1 code).

The full rules are in [docs/LANGUAGE.md](docs/LANGUAGE.md). Coming from Echo 1? See
[docs/MIGRATING.md](docs/MIGRATING.md).

## What's inside

| Part | What it does |
|---|---|
| `python/echo` | The language: lexer, parser, interpreter, checker, formatter, upgrader, REPL, command line |
| Biology | DNA/RNA/protein, ORFs, translation, Tm (nearest-neighbour, matches Biopython), primer design and checks, PCR programs, restriction enzymes and digests, alignment, protein mass / pI / GRAVY, FASTA, virtual gels, lab maths |
| Logic gates | `and or not xor nand nor xnor` as operators, truth tables, half/full adders, binary maths, bit tools |
| Cyber | hashes, Base64/hex, Caesar/Vigenère/XOR ciphers, password strength, entropy |
| Stats and ML | mean/median/stdev, correlation, linear fit, linear/logistic/kNN models, k-means clustering |
| AI | `ai.ask()`, `ai.code()` (AI writes Echo code), `ai.explain()` — with your own Claude, Gemini or OpenAI-compatible key |
| Converters | `echolang java` → Java (with `EchoRuntime.java`, ready for Android); `echolang python` → Python |
| `android/` | **Echo Lang** app: editor with highlighting, Run/Stop, Check, Format, examples, files, Java/Python conversion, AI key — runs offline |
| `vscode/echo-lang` | VS Code highlighting and snippets for `.echo` files |
| `docs/` | The language specification and the Echo 1 → 2 guide |

## Use it on a computer

```
cd python
pip install -e .
echolang                         # interactive mode
echolang examples                # list examples
echolang run echo/examples/bio.echo
echolang check my.echo           # errors and warnings, without running
echolang fmt my.echo             # tidy the layout
echolang upgrade old.echo -w     # Echo 1 -> Echo 2
echolang java my.echo -o My.java
echolang python my.echo -o my.py
```

Or without installing: `python -m echo FILE.echo` from the `python` folder.

**VS Code:** copy `vscode/echo-lang` into your `.vscode/extensions` folder (on Windows:
`%USERPROFILE%\.vscode\extensions\`), then restart VS Code.

## Use it on a phone

Install the APK from the `apk` branch or Releases. Every push to `main` runs the tests and builds it.

## Checked

- Automated tests: `cd python && python -m pytest -q`
- Every example passes `echolang check` and `echolang fmt --check`
- Tm matches Biopython `Tm_NN` exactly on 802 primers from GFP; protein mass and pI match `ProtParam`
- Converted Java and Python print exactly the same output as Echo for the examples
