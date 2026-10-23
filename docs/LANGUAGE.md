# Echo 2 Language Specification

Version 2.0 · October 2026

Echo is an English-like programming language for biology. It runs on a computer (`echolang`, written in
Python) and on Android (the Echo Lang app), and converts to Java or Python.

Echo 2 has **one way to write each thing**. Every rule below is the only form the language accepts; older
forms from Echo 1 stop with error **E104** and a hint showing the Echo 2 form. `echolang upgrade FILE`
rewrites Echo 1 files automatically (see [MIGRATING.md](MIGRATING.md)).

```echo
set gene: dna to bio.read_fasta("gfp.fasta")[0].seq
say "GC content: {bio.gc(gene)}%"

define best_pair(seq: dna) -> map
    return bio.design_primers(seq, product_min: 300, product_max: 700)
end

set pair to best_pair(gene)
if length(pair.problems) == 0 then
    say "Forward {pair.forward} · Reverse {pair.reverse} · {pair.product} bp"
end
```

---

## 1. Source files

- Files use the `.echo` extension and UTF-8 text.
- **One statement per line.** There is no statement separator such as `;`.
- A line may continue inside brackets `( )`, `[ ]`, `{ }`.
- Blocks (`if`, `while`, `for`, `repeat`, `define`, `try`) close with a plain `end`.
- Comments start with `#` and run to the end of the line.
- Indentation is not significant, but the standard layout (`echolang fmt`) uses 4 spaces per level.

### Names and keywords

Names are letters, digits and `_`, and don't start with a digit. Names are case-sensitive. By convention
variables and functions use `snake_case`; record names use `CapitalWords` (required).

Reserved keywords (can't be names, error **E105**):

```
set to say ask into if then else end repeat times while for each in from step break continue
define return try catch fail use as record fn add global and or not xor nand nor xnor
true false nothing is
```

`is` is reserved only so that Echo 1 code (`x is 3`) gets a clear message.

## 2. Values and types

| Type | Literal | Notes |
|---|---|---|
| `number` | `12`, `3.5`, `1_000_000`, `2e-3` | one number type; whole results print without `.0` |
| `integer` | `12` | a number with no fractional part (`2.0` counts) |
| `text` | `"hello"`, `"""many lines"""` | double quotes only; `{expr}` inside text is replaced by its value |
| `boolean` | `true`, `false` | the only values a condition accepts |
| `nothing` | `nothing` | the absence of a value |
| `list` | `[1, 2, 3]` | positions start at 0; negative positions count from the end |
| `map` | `{name: "gfp", length: 720}` | keys are text (bare names) or any value written as an expression |
| `function` | `fn(x) -> x * 2`, or a `define` | functions are values |
| record | `Gene("gfp", "ATG")` | made by a `record` declaration (section 6) |
| `module` | `bio`, `math`, a `use`d file | namespaces; not callable |

Biology types are text with a fixed alphabet (upper or lower case):

| Type | Allowed letters |
|---|---|
| `dna` | A C G T N |
| `rna` | A C G U N |
| `protein` | the 20 amino acids, B Z X U O, and `*` (stop) |

Text escapes: `\n` `\t` `\"` `\\` `\{` `\}`. Write `\{` for a literal curly bracket in text.

### Type expressions

```
number            dna              list of dna          map of number
text or nothing   any              Primer               list of Primer
```

`T or nothing` allows `nothing` as well as `T`. `any` accepts every value. A record name accepts records of
that record type.

## 3. Statements

### Variables

```echo
set count to 0                     # create or change a variable
set count to count + 1
set target_gc: number to 50        # optional type: later sets must match (E302)
set samples[0] to "leaf"           # list item
set plasmid.length to 2686         # map key or record field
add "root" to samples              # append to a list (lists only)
```

Variables set inside a function belong to that function. To change a top-level variable from inside a
function, write `global name` first.

### Output and input

```echo
say "GC is", bio.gc(seq), "%"      # values joined with single spaces
ask "Sample name?" into name       # numbers typed by the user become numbers
```

### Choices

```echo
if bio.gc(seq) > 60 then
    say "GC-rich"
else if bio.gc(seq) < 40 then
    say "AT-rich"
else
    say "balanced"
end
```

Conditions in `if`, `else if` and `while` must be `true` or `false`. A number, text or list is an error
(**E303**); compare explicitly instead: `if length(items) > 0 then`.

### Loops

```echo
repeat 3 times ... end
while count > 0 ... end
for each base in "ATGC" ... end            # items of a list, letters of text, keys of a map
for each key, value in {a: 1, b: 2} ... end
for each position, item in ["x", "y"] ... end
for i from 1 to 10 step 2 ... end          # both ends included; step may be negative
```

`break` leaves the innermost loop; `continue` starts its next round. Using either outside a loop is
**E107**.

### Functions

```echo
define melting(primer: dna, salt: number = 50) -> number
    return bio.tm(primer, na: salt)
end

say melting("AGAGTTTGATCATGGCTCAG")
say melting("AGAGTTTGATCATGGCTCAG", salt: 100)     # named value

set square to fn(n) -> n * n                        # a one-expression function
```

- Parameters with a default come after those without.
- Calls pass positional values first, then named values (`name: value`).
- Parameter and result types are optional and checked on every call (**E302**).
- `return` with no value returns `nothing`. Using `return` outside a function is **E107**.
- Functions are closures: they remember the variables around them.

### Errors

```echo
try
    say bio.translate("ATGXYZ")
catch problem
    say problem.code, problem.message, problem.line
end

fail "Primer is too short"                         # raises E407 with this message
```

The caught value is an `Error` record with fields `code`, `message` and `line`. `catch` without a name is
allowed.

### Using other files

```echo
use "helpers.echo"                 # available as helpers.something
use "lab/maths.echo" as lab        # choose the module name
```

The file runs once in its own scope; its top-level names (not starting with `_`) become module members.
Paths are relative to the file that uses them. Built-in modules need no `use`.

## 4. Expressions and operators

From lowest to highest precedence:

| Operators | Meaning |
|---|---|
| `or` `nor` `xor` `xnor` | logic gates |
| `and` `nand` | logic gates |
| `not` | logic not |
| `==` `!=` `<` `>` `<=` `>=` `in` `not in` | comparison and membership |
| `+` `-` | add, subtract; `+` also joins text, lists and maps |
| `*` `/` `//` `%` | multiply, divide, whole division, remainder |
| `-` (unary) | negative |
| `^` | power (right-associative) |
| `f(x)` `items[i]` `items[a:b]` `value.name` | call, index, slice, field or module member |

Rules:

- Arithmetic needs numbers (**E301**). `+` with text on either side joins as text: `"GC " + 50`.
- `/` gives a whole number when the division is exact (`6 / 2` is `3`) and a decimal otherwise.
- Division by zero is **E401**.
- `<` `>` `<=` `>=` compare two numbers or two texts.
- `==` never treats `true` as `1`.
- `in` looks for an item in a list, a key in a map, or exact text inside text (case-sensitive).
- Gates take two booleans (result boolean) or two bits `0`/`1` (result bit). Mixing is **E301**.
  `and` and `or` stop early when the left side decides the answer.
- Slices `items[a:b]` include `a` and exclude `b`; either may be left out.
- There are no method calls on values: write `upper(name)`, not `name.upper()`. `.name` reads a field of a
  map or record, or a member of a module.

## 5. Modules and built-in functions

A few everyday functions are global; everything else lives in a module:

```echo
say length(items), upper("atg"), range(1, 5)
say bio.gc(seq), math.sqrt(2), random.integer(1, 6), stats.mean(values), cyber.sha256(text)
```

| Module | What it holds |
|---|---|
| `bio` | DNA, RNA, proteins, primers, PCR, enzymes, gels, FASTA, lab maths |
| `math` | `sqrt`, `round`, `floor`, `ceil`, `log`, `sin`, `pi`, `e` ... |
| `random` | random numbers, choices, shuffling, `seed` |
| `stats` | mean, median, standard deviation, correlation, straight-line fits |
| `ml` | small models: linear, logistic, kNN, k-means |
| `gates` | logic gates, truth tables, adders, binary and bits |
| `cyber` | hashes, encodings, classic ciphers, password checks |
| `file` | read and write files |
| `json` | JSON text to values and back |
| `time` | date, time, waiting |
| `ai` | ask Claude, Gemini or an OpenAI-compatible AI with your own key |

Positions returned by biology functions start at 1 (as in biology papers); list positions start at 0.
Inside Echo, `help()` lists everything, `help("bio")` lists a module and `help("bio.gc")` explains one
function. The full list is in section 10.

## 6. Records

```echo
record Primer(name: text, seq: dna, tm: number = 0)

set p to Primer("27F", "AGAGTTTGATCATGGCTCAG")
set p.tm to bio.tm(p.seq)
say p                      # Primer(name: "27F", seq: "AGAGTTTGATCATGGCTCAG", tm: 49.36)
say type(p)                # Primer
```

- Fields without a default must be given (**E205**).
- A record has exactly its declared fields: reading or setting another field is **E202**.
- Field types are checked when the record is made and whenever a field is set (**E302**).

## 7. Errors

Every error has a code, a line and usually a hint:

```
Error E201 at line 3: Unknown name 'gcc'.
  Hint: Did you mean 'gc'?
```

`echolang explain E201` prints the explanation of any code.

| Code | Meaning |
|---|---|
| E101 | Syntax error |
| E102 | Block has no `end` |
| E103 | Unclosed text or bracket |
| E104 | Echo 1 syntax (the hint shows the Echo 2 form) |
| E105 | Keyword used as a name |
| E106 | Can't set this |
| E107 | `break`/`continue` outside a loop, `return` outside a function |
| E201 | Unknown name |
| E202 | Unknown module member or field |
| E203 | Wrong number of values |
| E204 | Unknown named value (setting) |
| E205 | Missing value |
| E206 | Not a function |
| E301 | Wrong type for an operation |
| E302 | Value doesn't match a declared type |
| E303 | Condition is not `true`/`false` |
| E304 | Unknown type |
| E401 | Division by zero |
| E402 | Position out of range |
| E403 | Missing map key |
| E404 | A built-in function rejected a value |
| E405 | Too much recursion |
| E406 | Stopped by the user |
| E407 | Raised by `fail` |
| E501 | File problem |
| E502 | AI problem |

Warnings, reported only by `echolang check`:

| Code | Meaning |
|---|---|
| W101 | A variable inside a function is set but never used |
| W102 | Unreachable code after `return`, `break`, `continue` or `fail` |
| W103 | A line computes a value and throws it away |
| W104 | A name hides a built-in function or module |
| W105 | A function with a result type can end without `return` |

## 8. Tools

```
echolang FILE.echo                 run
echolang check FILE.echo           find errors and warnings without running (exit code 1 on errors)
echolang fmt FILE.echo             rewrite in the standard layout   (--check: only report)
echolang upgrade FILE.echo -w      convert Echo 1 code to Echo 2
echolang explain E302              explain an error code
echolang java FILE.echo -o F.java  convert to Java (needs echo/EchoRuntime.java: echolang java --runtime DIR)
echolang python FILE.echo -o f.py  convert to Python (needs this package installed)
echolang help bio                  list a module
```

The **checker** reports unknown names and members, wrong numbers of values, unknown settings, unknown
types, and type mismatches it can prove from the code (literals, typed variables, typed function results).
Everything else is still checked when the program runs.

The **formatter** sets 4-space indentation, one space around operators and after commas, no spaces inside
brackets, keeps comments, and allows at most one blank line in a row. Formatting twice gives the same text.

Converted **Java** and **Python** programs keep Echo's behaviour, including type checks and error codes.
The Java converter needs `define` at the top level, doesn't support `use` yet, and a `fn(...) -> ...` there
can read but not change the variables around it.

## 9. Grammar

```ebnf
program     = { statement NEWLINE } ;
statement   = set | add | say | ask | if | repeat | while | for | define | return | try | fail
            | use | record | global | "break" | "continue" | call ;
set         = "set" target [ ":" type ] "to" expr ;
target      = NAME { "." NAME | "[" expr "]" } ;
add         = "add" expr "to" target ;
say         = "say" [ expr { "," expr } ] ;
ask         = "ask" expr "into" NAME ;
if          = "if" expr "then" block { "else" "if" expr "then" block } [ "else" block ] "end" ;
repeat      = "repeat" expr "times" block "end" ;
while       = "while" expr block "end" ;
for         = "for" "each" NAME [ "," NAME ] "in" expr block "end"
            | "for" NAME "from" expr "to" expr [ "step" expr ] block "end" ;
define      = "define" NAME params [ "->" type ] block "end" ;
params      = "(" [ param { "," param } ] ")" ;
param       = NAME [ ":" type ] [ "=" expr ] ;
return      = "return" [ expr ] ;
try         = "try" block [ "catch" [ NAME ] block ] "end" ;
fail        = "fail" expr ;
use         = "use" STRING [ "as" NAME ] ;
record      = "record" NAME params ;
global      = "global" NAME { "," NAME } ;
type        = NAME [ "of" type ] [ "or" "nothing" ] | "nothing" ;

expr        = or_expr ;
or_expr     = and_expr { ( "or" | "nor" | "xor" | "xnor" ) and_expr } ;
and_expr    = not_expr { ( "and" | "nand" ) not_expr } ;
not_expr    = "not" not_expr | comparison ;
comparison  = sum { ( "==" | "!=" | "<" | ">" | "<=" | ">=" | "in" | "not" "in" ) sum } ;
sum         = product { ( "+" | "-" ) product } ;
product     = unary { ( "*" | "/" | "//" | "%" ) unary } ;
unary       = "-" unary | power ;
power       = postfix [ "^" unary ] ;
postfix     = primary { "(" args ")" | "[" expr "]" | "[" [ expr ] ":" [ expr ] "]" | "." NAME } ;
args        = [ arg { "," arg } ] ;
arg         = expr | NAME ":" expr ;
primary     = NUMBER | STRING | NAME | "true" | "false" | "nothing" | "(" expr ")"
            | "[" [ expr { "," expr } ] "]" | "{" [ key ":" expr { "," key ":" expr } ] "}"
            | "fn" params "->" expr ;
key         = NAME | expr ;
```

## 10. Built-in reference

<!-- generated by docs/make_reference.py; do not edit by hand -->

### Global functions

| Function | What it does |
|---|---|
| `append(list, item)` | adds to the end |
| `boolean(x)` | true or false |
| `chars(text)` | list of letters |
| `code(letter)` | character code |
| `contains(text or list, item)` |  |
| `copy(list or map)` | a separate copy |
| `count(list or text, item)` |  |
| `ends_with(text, end)` |  |
| `filter(list, fn)` | keeps items where fn is true |
| `find(text, part)` | first position or -1 |
| `flatten(list of lists)` |  |
| `format(number, places)` | fixed decimals as text |
| `get(map or list, key, default=nothing)` |  |
| `has(map, key)` |  |
| `help()` | lists everything; help("bio") lists a module; help("bio.gc") explains one function |
| `index_of(list or text, item)` | position or -1 |
| `insert(list, position, item)` |  |
| `integer(x)` | whole number (cuts the decimals) |
| `join(list, separator="")` |  |
| `keys(map)` |  |
| `length(x)` | counts letters, items or keys |
| `letter(code)` | character from code |
| `lower(text)` |  |
| `map(list, fn)` | applies fn to each item |
| `max(list)` | or max(a, b, ...) |
| `min(list)` | or min(a, b, ...) |
| `number(x)` | turns text into a number |
| `pad(text, width, fill=" ")` | pads on the right (negative width pads left) |
| `pop(list, position=-1)` | removes and returns an item |
| `range(a, b, step=1)` | list from a to b (b included) |
| `reduce(list, fn, start)` |  |
| `remove(list or map, item or key)` |  |
| `replace(text, old, new)` |  |
| `reverse(list or text)` |  |
| `slice(x, start, end)` | part of a list or text |
| `sort(list, key=nothing, reverse=false)` | new sorted list |
| `split(text, separator=spaces)` |  |
| `starts_with(text, start)` |  |
| `sum(list)` |  |
| `text(x)` | turns any value into text |
| `trim(text)` | removes spaces at both ends |
| `type(x)` | -> number, text, boolean, list, map, nothing, function, or a record name |
| `unique(list)` | without repeats, order kept |
| `upper(text)` |  |
| `values(map)` |  |
| `zip(a, b)` | pairs items: [[a0, b0], ...] |

### bio — DNA, RNA, proteins, primers, PCR, enzymes, gels, FASTA, lab maths

| Function | What it does |
|---|---|
| `bio.align(a, b, match=1, mismatch=-1, gap=-2)` | global alignment map |
| `bio.amino_name("M")` | -> Met |
| `bio.at(seq)` | AT content in % |
| `bio.back_transcribe(rna)` | -> DNA |
| `bio.base_counts(seq)` | map of A, C, G, T counts |
| `bio.charge_at(protein, ph=7)` | net charge |
| `bio.codon_table()` | map of codon -> amino acid |
| `bio.codon_usage(seq)` | map codon -> count (frame 1) |
| `bio.complement(seq)` |  |
| `bio.copy_number(ng, length_bp)` | copies of double-stranded DNA |
| `bio.design_primers(seq, product_min=100, product_max=1000, tm_opt=60, gc_min=40, gc_max=60)` | best primer pair |
| `bio.digest(seq, enzyme or list, circular=false)` | fragment sizes, largest first |
| `bio.dilute(c1, c2, v2)` | volume of stock to take (C1V1 = C2V2) |
| `bio.dna(text)` | cleans a sequence: upper case, no spaces, numbers or FASTA header |
| `bio.dna_mass(seq, double=false)` | mass in g/mol (single strand unless double=true) |
| `bio.enzymes()` | list of known restriction enzymes |
| `bio.find_motif(seq, motif)` | 1-based positions; motif may use IUPAC codes like N, R, Y |
| `bio.find_orfs(seq, min_aa=30)` | open reading frames on both strands (positions 1-based) |
| `bio.gc(seq)` | GC content in % (2 decimals) |
| `bio.gc_count(seq)` | how many G and C bases |
| `bio.gel(lanes, ladder=true)` | draws an agarose gel; lanes = list of sizes or list of lists |
| `bio.gravy(protein)` | hydropathy (Kyte-Doolittle average); above 0 = water-repelling |
| `bio.hamming(a, b)` | number of differences between two equal-length sequences |
| `bio.is_dna(text)` | true if only A C G T (N allowed) |
| `bio.isoelectric_point(protein)` | pI |
| `bio.molarity(mass_g, mol_weight, volume_l)` | in mol/L |
| `bio.mutate(seq, position, base)` | change one base (position 1-based) |
| `bio.parse_fasta(text)` | list of {name, seq} |
| `bio.pcr_program(forward, reverse, product_bp, polymerase="taq")` | text table |
| `bio.primer_check(primer)` | list of problems (empty list = good primer) |
| `bio.primer_info(primer)` | map: length, gc, gc_count, tm, problems |
| `bio.protein_info(protein)` | map: length, mass, pi, gravy, charge_7 |
| `bio.protein_mass(protein)` | average mass in Da |
| `bio.random_dna(length, gc=50)` | random sequence |
| `bio.read_fasta(path)` | list of {name, seq} |
| `bio.restriction_sites(seq)` | map enzyme -> cut positions (only enzymes that cut) |
| `bio.reverse_complement(seq)` | the other strand, read 5'->3' |
| `bio.start_codon` | constant: `"ATG"` |
| `bio.stop_codons` | constant: `["TAA", "TAG", "TGA"]` |
| `bio.tm(primer, na=50, primer_nm=25)` | melting temperature in °C (nearest-neighbour) |
| `bio.tm_basic(primer)` | Wallace rule 2(A+T) + 4(G+C) |
| `bio.to_fasta(name, seq)` | FASTA text (60 letters per line) |
| `bio.transcribe(dna)` | -> mRNA (T becomes U) |
| `bio.translate(seq, frame=1, to_stop=false)` | -> protein (* = stop) |
| `bio.write_fasta(path, records)` | records = list of {name, seq} |

### ai — ask Claude, Gemini or an OpenAI-compatible AI (your own key)

| Function | What it does |
|---|---|
| `ai.ask(question)` | asks your AI and returns its answer as text |
| `ai.code(task)` | asks the AI to write Echo code for a task (returns the code as text) |
| `ai.explain(text)` | explains code, a sequence or a result in simple words |
| `ai.setup(provider, key, model=nothing, url=nothing)` | saves your AI key on this device |
| `ai.status()` | shows which AI is set up (never shows the key) |

### cyber — hashes, encodings, classic ciphers, password checks

| Function | What it does |
|---|---|
| `cyber.base64_decode(text)` |  |
| `cyber.base64_encode(text)` |  |
| `cyber.caesar(text, shift)` | Caesar cipher (negative shift decodes) |
| `cyber.caesar_crack(text)` | list of all 26 shifts to read by eye |
| `cyber.entropy(text)` | Shannon entropy in bits per character |
| `cyber.hex_decode(hex)` | -> text |
| `cyber.hex_encode(text)` | -> hex |
| `cyber.is_valid_ip(text)` | true for a valid IPv4 address |
| `cyber.md5(text)` | hash as hex |
| `cyber.password_strength(pw)` | map: score 0-4, label, tips |
| `cyber.random_password(length=16)` | strong random password |
| `cyber.rot13(text)` |  |
| `cyber.sha1(text)` | hash as hex |
| `cyber.sha256(text)` | hash as hex |
| `cyber.sha512(text)` | hash as hex |
| `cyber.vigenere(text, key, decode=false)` |  |
| `cyber.xor_cipher(text, key)` | -> hex; cyber.xor_decipher(hex, key) reverses it |
| `cyber.xor_decipher(hex, key)` |  |

### file — read and write files on this device

| Function | What it does |
|---|---|
| `file.append(path, text)` |  |
| `file.exists(path)` |  |
| `file.read(path)` | text of a file |
| `file.read_csv(path)` | list of maps (first row is the header) |
| `file.write(path, text)` |  |

### gates — logic gates, truth tables, adders, binary and bits

| Function | What it does |
|---|---|
| `gates.add_binary("1011", "0110")` | adds two binary numbers with full adders |
| `gates.bit_and(a, b)` | bitwise AND |
| `gates.bit_not(a, bits=8)` | flips every bit |
| `gates.bit_or(a, b)` | bitwise OR |
| `gates.bit_xor(a, b)` | bitwise XOR |
| `gates.count_ones(n)` | how many 1 bits |
| `gates.from_binary("1011")` | -> 11 |
| `gates.from_hex("ff")` | -> 255 |
| `gates.full_adder(a, b, carry_in)` | -> {sum, carry} |
| `gates.gate(name, a, b)` | runs a gate by name: and, or, xor, nand, nor, xnor, not |
| `gates.half_adder(a, b)` | -> {sum, carry} |
| `gates.shift_left(a, n)` |  |
| `gates.shift_right(a, n)` |  |
| `gates.to_binary(n, bits=0)` | binary text, padded to bits |
| `gates.to_hex(n)` | hexadecimal text |
| `gates.truth_table(fn or gate name, inputs=2)` | table of every input combination (show it with say) |

### json — turn JSON text into values and back

| Function | What it does |
|---|---|
| `json.format(value)` | JSON text |
| `json.parse(text)` | map/list from JSON |

### math — numbers: sqrt, round, floor, ceil, log, sin, pi, e

| Function | What it does |
|---|---|
| `math.abs(x)` |  |
| `math.ceil(x)` |  |
| `math.cos(x)` |  |
| `math.e` | constant: `2.718281828` |
| `math.exp(x)` |  |
| `math.floor(x)` |  |
| `math.log(x, base=e)` |  |
| `math.log10(x)` |  |
| `math.pi` | constant: `3.141592654` |
| `math.round(x, places=0)` |  |
| `math.sin(x)` |  |
| `math.sqrt(x)` |  |
| `math.tan(x)` |  |

### ml — small machine-learning models: linear, logistic, kNN, k-means

| Function | What it does |
|---|---|
| `ml.accuracy(model, X, y)` | fraction correct (classifiers)  |
| `ml.cluster(points, k, seed=1)` | k-means -> {labels, centers} |
| `ml.error(model, X, y)` | mean absolute error (regression) |
| `ml.predict(model, x)` | prediction for one example (a number or a list of features) |
| `ml.probability(model, x)` | chance of class 1 for a logistic model |
| `ml.split_data(X, y, test=0.25, seed=1)` | -> {X_train, y_train, X_test, y_test} |
| `ml.train(kind, X, y, ...)` | kind: "linear", "logistic", "knn" -> model map |

### random — random numbers, choices and shuffling

| Function | What it does |
|---|---|
| `random.choose(list)` | random item |
| `random.integer(a, b)` | whole number from a to b |
| `random.number()` | number from 0 to 1 |
| `random.seed(n)` | makes random results repeatable |
| `random.shuffle(list)` | new list in random order |

### stats — mean, median, standard deviation, correlation, straight-line fits

| Function | What it does |
|---|---|
| `stats.correlation(xs, ys)` | Pearson r |
| `stats.linear_fit(xs, ys)` | -> {slope, intercept, r2} straight line |
| `stats.mean(list)` | average |
| `stats.median(list)` |  |
| `stats.mode(list)` | most common value |
| `stats.normalize(list)` | scales numbers to 0..1 |
| `stats.stdev(list)` | sample standard deviation |
| `stats.variance(list)` | sample variance |
| `stats.zscore(list)` | (x - mean) / stdev |

### time — date, time and waiting

| Function | What it does |
|---|---|
| `time.clock()` | seconds, for timing code |
| `time.now()` | date and time as text |
| `time.today()` | date as text |
| `time.wait(seconds)` |  |
