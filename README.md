# Echo

**An English-like programming language for biology** — with logic gates, cyber-security tools,
machine learning and AI built in. Write it on your phone or laptop, then convert it to Java or Python.

```echo
set gene to read_fasta("gfp.fasta")[0]
say "GC content: {gc(gene)}%"

set pair to design_primers(gene, product_min: 300, product_max: 700)
say "Forward {pair.forward}  GC {pair.gc_forward}%  Tm {pair.tm_forward} °C"
say "Reverse {pair.reverse}  GC {pair.gc_reverse}%  Tm {pair.tm_reverse} °C"

if length(pair.problems) == 0 then
    say "Both primers pass every check."
end
```

## What's inside

| Part | What it does |
|---|---|
| `python/echo` | The language: lexer, parser, interpreter, 170+ built-in functions, REPL, command line |
| Biology | DNA/RNA/protein, ORFs, translation, Tm (nearest-neighbour, matches Biopython), primer design and checks, PCR programs, restriction enzymes and digests, alignment, protein mass / pI / GRAVY, FASTA, virtual gels, lab maths |
| Logic gates | `and or not xor nand nor xnor` as operators, truth tables, half/full adders, binary maths, bit tools |
| Cyber | hashes, Base64/hex, Caesar/Vigenère/XOR ciphers, password strength, entropy |
| ML | mean/median/stdev, correlation, linear fit, linear/logistic/kNN models, k-means clustering |
| AI | `ai()`, `ask ai ... into`, `ai_code()` (AI writes Echo code), `ai_explain()` — with your own Claude, Gemini or OpenAI-compatible key |
| Converters | `echolang java` → Java (with `EchoRuntime.java`, ready for Android); `echolang python` → Python |
| `android/` | **Echo Lang** app: editor with highlighting, Run/Stop, examples, files, Java/Python conversion, AI key — runs offline |
| `vscode/echo-lang` | VS Code highlighting and snippets for `.echo` files |
| `docs/LANGUAGE.md` | The full language guide and every function |

## Use it on a computer

```
cd python
pip install -e .
echolang                       # interactive mode
echolang examples              # list examples
echolang run echo/examples/bio.echo
echolang java my.echo -o My.java
echolang python my.echo -o my.py
```

Or without installing: `python -m echo FILE.echo` from the `python` folder.

**VS Code:** copy `vscode/echo-lang` into your `.vscode/extensions` folder (on Windows:
`%USERPROFILE%\.vscode\extensions\`), then restart VS Code.

## Use it on a phone

Install the APK from the `apk` branch or Releases. Every push to `main` runs the tests and builds it.

## Checked

- 36 automated tests (`cd python && python -m pytest -q`)
- Tm matches Biopython `Tm_NN` exactly on 802 primers from GFP; protein mass and pI match `ProtParam`
- Converted Java and Python print exactly the same output as Echo for the examples
