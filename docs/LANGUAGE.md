# The Echo language

Echo is an English-like programming language for biology. It reads like plain sentences, runs on a
laptop (Python) or a phone (the Echo Lang app), and converts to Java or Python when you need them.

```echo
set gene to dna("ATGGCTAGCAAAGGAGAAGAACTTTTCACTGGAGTTGTCCCAATTCTTGTTGAATTAGATGGTTAA")
say "GC is {gc(gene)}%"
for each orf in find_orfs(gene, 10)
    say "ORF {orf.start}-{orf.end}: {orf.protein}"
end
```

## 1. Basics

- One statement per line. Blocks (`if`, loops, `define`, `try`) close with `end`.
  You may write `end if`, `end for` and so on if it helps you read.
- Comments start with `#`.
- Names are made of letters, numbers and `_`. Echo words (like `set`, `to`, `step`) can't be names.

| Kind | Examples |
|---|---|
| number | `12`, `3.5`, `1_000_000`, `2e-3` |
| text | `"hello"`, `'hi'`, `"""many lines"""` |
| yes/no | `true`, `false` (also `yes`, `no`) |
| nothing | `nothing` |
| list | `[1, 2, 3]` — positions start at 0: `items[0]`, `items[-1]`, `items[1:3]` |
| map | `{name: "gfp", length: 720}` — `m.name` or `m["name"]` |
| function | `fn(x) -> x * 2` or a `define` |

Text can hold code inside `{}`: `say "next year: {age + 1}"`. Write `\{` for a real bracket.

## 2. Statements

```echo
set x to 5            # or: x = 5
x += 1                # also -=  *=  /=   (set x += 1 works too)
add 4 to numbers      # append to a list (or add to a number / text)
say "x is", x         # prints values separated by spaces
ask "Your name?" into name        # numbers you type become numbers
ask ai "What is a plasmid?" into answer   # needs your AI key
```

### Choices

```echo
if gc(seq) > 60 then
    say "GC-rich"
else if gc(seq) < 40 then
    say "AT-rich"
else
    say "balanced"
end
```

### Loops

```echo
repeat 3 times ... end
repeat forever ... end          # leave with break
while count > 0 ... end
for each base in "ATGC" ... end
for each name, value in {a: 1, b: 2} ... end
for each i, item in ["x", "y"] ... end   # position and item
for i from 1 to 10 step 2 ... end        # the end value is included
```

`break` (or `stop`) leaves the loop. `continue` (or `skip`) jumps to the next round.

### Functions

```echo
define melting(primer, salt = 50)
    return tm(primer, na: salt)
end
say melting("AGAGTTTGATCATGGCTCAG")
say melting("AGAGTTTGATCATGGCTCAG", salt: 100)

set square to fn(n) -> n * n
say map([1, 2, 3], square)
```

Variables you set inside a function belong to that function. To change a top-level variable,
write `global name` first. Functions can return functions (closures).

Three ways to call a function: `gc(seq)`, `gc of seq`, and `seq.gc()`.

### Records

```echo
record Sample(name, seq, gc = 0)
set s to Sample("plasmid A", "ATGCC")
set s.gc to gc(s.seq)
say s            # Sample(name: "plasmid A", seq: "ATGCC", gc: 60)
```

### Errors

```echo
try
    say translate("ATGXYZ")
catch problem
    say "Could not translate:", problem
end
fail "Stop here with this message"
```

Echo's own error messages give the line number and a hint, for example
`Line 3: I don't know 'gcc'. Hint: Did you mean 'gc'?`

### Other files

`use "helpers.echo"` runs another file so its functions can be used.

## 3. Operators

| | |
|---|---|
| Maths | `+ - * / // % ^` (`/` gives a whole number when it divides exactly; `^` is power) |
| Join | `"GC " + 50` makes text; lists and maps join with `+` |
| Compare | `== != < > <= >=`, `is`, `is not` |
| Inside | `"ATG" in seq`, `x not in list` (DNA text is matched ignoring case) |
| Logic gates | `and or not xor nand nor xnor` |

Gates work on yes/no values and on bits: `1 xor 0` is `1`, `true xor false` is `true`.

## 4. Converting to Java and Python

```
echolang java gene.echo -o Gene.java       # Java class with a main() and a run()
echolang java --runtime .                  # writes echo/EchoRuntime.java (needed once)
javac -d out Gene.java echo/EchoRuntime.java && java -cp out Gene

echolang python gene.echo -o gene.py       # Python that uses the echo package
```

The Java runtime has the core, biology, gates, cyber, statistics, ML and `ai()` functions, so a
converted program prints the same output as Echo. In an Android app, copy `echo/EchoRuntime.java`
into `app/src/main/java/echo/`, set `EchoRuntime.out` to show text in your UI, and call `Gene.run()`
on a background thread.

Rules for Java: put `define` at the top level, and a `fn(...) -> ...` can read but not change
the variables around it.

## 5. AI

`ai_setup("claude", "YOUR-KEY")` saves your key in `~/.echo/config.json` on your own computer
(or set `ECHO_AI_PROVIDER` and `ECHO_AI_KEY`). Providers: `claude`, `gemini`, `openai`
(OpenAI-compatible; set a custom `url` for others). In the app, tap **AI key**. Never put a key
inside code you share.

- `ai(question)` returns the answer as text
- `ai_code(task)` asks the AI to write Echo code for a task
- `ai_explain(text)` explains code, a sequence or a result simply

## 6. All built-in functions

Positions returned by biology functions start at 1 (as in biology); list positions start at 0.
`help()` lists everything inside Echo; `help("gc")` explains one function.

### Core (text, numbers, lists, maps, files, time)

| Function | What it does |
|---|---|
| `print(a, b, ...)` | shows values, like say |
| `input(prompt)` | asks the user and returns text |
| `type(x)` | -> number, text, list, map, yes/no, nothing, function |
| `length(x)` | counts letters, items or keys |
| `text(x)` | turns any value into text |
| `number(x)` | turns text into a number |
| `int(x)` | whole number (cuts the decimals) |
| `bool(x)` | true or false |
| `abs(x)` |  |
| `round(x, places=0)` |  |
| `floor(x)` |  |
| `ceil(x)` |  |
| `sqrt(x)` |  |
| `sin(x)` |  |
| `cos(x)` |  |
| `tan(x)` |  |
| `exp(x)` |  |
| `log(x, base=e)` |  |
| `log10(x)` |  |
| `pi = 3.14159...` |  |
| `e = 2.71828...` |  |
| `min(list)` | or min(a, b, ...) |
| `max(list)` | or max(a, b, ...) |
| `sum(list)` |  |
| `random()` | number from 0 to 1 |
| `random_int(a, b)` | whole number from a to b |
| `choose(list)` | random item |
| `shuffle(list)` | new list in random order |
| `seed(n)` | makes random results repeatable |
| `range(a, b, step=1)` | list from a to b (b included) |
| `append(list, item)` | adds to the end |
| `pop(list, position=-1)` | removes and returns an item |
| `insert(list, position, item)` |  |
| `remove(list or map, item or key)` |  |
| `sort(list, key=nothing, reverse=false)` | new sorted list |
| `reverse(list or text)` |  |
| `map(list, fn)` | applies fn to each item |
| `filter(list, fn)` | keeps items where fn is true |
| `reduce(list, fn, start)` |  |
| `unique(list)` | without repeats, order kept |
| `zip(a, b)` | pairs items: [[a0, b0], ...] |
| `index_of(list or text, item)` | position or -1 |
| `count(list or text, item)` |  |
| `slice(x, start, end)` | part of a list or text |
| `flatten(list of lists)` |  |
| `upper(text)` |  |
| `lower(text)` |  |
| `trim(text)` | removes spaces at both ends |
| `split(text, separator=spaces)` |  |
| `join(list, separator='')` |  |
| `replace(text, old, new)` |  |
| `contains(text or list, item)` |  |
| `starts_with(text, start)` |  |
| `ends_with(text, end)` |  |
| `find(text, part)` | first position or -1 |
| `pad(text, width, fill=' ')` | pads on the right (negative width pads left) |
| `format(number, places)` | fixed decimals as text |
| `chars(text)` | list of letters |
| `code(letter)` | character code |
| `letter(code)` | character from code |
| `keys(map)` |  |
| `values(map)` |  |
| `has(map, key)` |  |
| `get(map or list, key, default=nothing)` |  |
| `copy(list or map)` | a separate copy |
| `read_file(path)` | text of a file |
| `write_file(path, text)` |  |
| `append_file(path, text)` |  |
| `file_exists(path)` |  |
| `from_json(text)` | map/list from JSON |
| `to_json(value)` | JSON text |
| `read_csv(path)` | list of maps (first row is the header) |
| `now()` | date and time as text |
| `today()` | date as text |
| `clock()` | seconds, for timing code |
| `wait(seconds)` |  |
| `help()` | lists all functions; help(name) explains one |

### Biology

| Function | What it does |
|---|---|
| `dna(text)` | cleans a sequence: upper case, no spaces, numbers or FASTA header |
| `is_dna(text)` | true if only A C G T (N allowed) |
| `gc(seq)` | GC content in % (2 decimals) |
| `at(seq)` | AT content in % |
| `gc_count(seq)` | how many G and C bases |
| `base_counts(seq)` | map of A, C, G, T counts |
| `complement(seq)` |  |
| `reverse_complement(seq)` | the other strand, read 5'->3' |
| `transcribe(dna)` | -> mRNA (T becomes U) |
| `back_transcribe(rna)` | -> DNA |
| `translate(seq, frame=1, to_stop=false)` | -> protein (* = stop) |
| `codon_table()` | map of codon -> amino acid |
| `amino_name('M')` | -> Met |
| `codon_usage(seq)` | map codon -> count (frame 1) |
| `find_orfs(seq, min_aa=30)` | open reading frames on both strands (positions 1-based) |
| `find_motif(seq, motif)` | 1-based positions; motif may use IUPAC codes like N, R, Y |
| `hamming(a, b)` | number of differences between two equal-length sequences |
| `mutate(seq, position, base)` | change one base (position 1-based) |
| `random_dna(length, gc=50)` | random sequence |
| `tm(primer, na=50, primer_nm=25)` | melting temperature in °C (nearest-neighbour) |
| `tm_basic(primer)` | Wallace rule 2(A+T) + 4(G+C) |
| `primer_check(primer)` | list of problems (empty list = good primer) |
| `primer_info(primer)` | map: length, gc, gc_count, tm, problems |
| `design_primers(seq, product_min=100, product_max=1000, tm_opt=60, gc_min=40, gc_max=60)` | best primer pair |
| `pcr_program(forward, reverse, product_bp, polymerase='taq')` | text table |
| `enzymes()` | list of known restriction enzymes |
| `restriction_sites(seq)` | map enzyme -> cut positions (only enzymes that cut) |
| `digest(seq, enzyme or list, circular=false)` | fragment sizes, largest first |
| `align(a, b, match=1, mismatch=-1, gap=-2)` | global alignment map |
| `protein_mass(protein)` | average mass in Da |
| `isoelectric_point(protein)` | pI |
| `charge_at(protein, ph=7)` | net charge |
| `gravy(protein)` | hydropathy (Kyte-Doolittle average); above 0 = water-repelling |
| `protein_info(protein)` | map: length, mass, pi, gravy, charge_7 |
| `dna_mass(seq, double=false)` | mass in g/mol (single strand unless double=true) |
| `dilute(c1, c2, v2)` | volume of stock to take (C1V1 = C2V2) |
| `copy_number(ng, length_bp)` | copies of double-stranded DNA |
| `molarity(mass_g, mol_weight, volume_l)` | in mol/L |
| `parse_fasta(text)` | list of {name, seq} |
| `read_fasta(path)` | list of {name, seq} |
| `to_fasta(name, seq)` | FASTA text (60 letters per line) |
| `write_fasta(path, records)` | records = list of {name, seq} |
| `gel(lanes, ladder=true)` | draws an agarose gel; lanes = list of sizes or list of lists |
| `start_codon = ATG` |  |
| `stop_codons = TAA,` | TAG, TGA |

### Logic gates and bits

| Function | What it does |
|---|---|
| `gate(name, a, b)` | runs a gate by name: and, or, xor, nand, nor, xnor, not |
| `truth_table(fn or gate name, inputs=2)` | table of every input combination (show it with say) |
| `half_adder(a, b)` | -> {sum, carry} |
| `full_adder(a, b, carry_in)` | -> {sum, carry} |
| `add_binary('1011', '0110')` | adds two binary numbers with full adders |
| `bit_and(a, b)` | bitwise AND |
| `bit_or(a, b)` | bitwise OR |
| `bit_xor(a, b)` | bitwise XOR |
| `bit_not(a, bits=8)` | flips every bit |
| `shift_left(a, n)` |  |
| `shift_right(a, n)` |  |
| `to_binary(n, bits=0)` | binary text, padded to bits |
| `from_binary('1011')` | -> 11 |
| `to_hex(n)` | hexadecimal text |
| `from_hex('ff')` | -> 255 |
| `count_ones(n)` | how many 1 bits |

### Cyber-security

| Function | What it does |
|---|---|
| `md5(text)` | hash as hex |
| `sha1(text)` | hash as hex |
| `sha256(text)` | hash as hex |
| `sha512(text)` | hash as hex |
| `base64_encode(text)` |  |
| `base64_decode(text)` |  |
| `hex_encode(text)` | -> hex |
| `hex_decode(hex)` | -> text |
| `caesar(text, shift)` | Caesar cipher (negative shift decodes) |
| `rot13(text)` |  |
| `caesar_crack(text)` | list of all 26 shifts to read by eye |
| `vigenere(text, key, decode=false)` |  |
| `xor_cipher(text, key)` | -> hex; xor_decipher(hex, key) reverses it |
| `xor_decipher(hex, key)` |  |
| `entropy(text)` | Shannon entropy in bits per character |
| `password_strength(pw)` | map: score 0-4, label, tips |
| `random_password(length=16)` | strong random password |
| `is_valid_ip(text)` | true for a valid IPv4 address |

### Statistics and machine learning

| Function | What it does |
|---|---|
| `mean(list)` | average |
| `median(list)` |  |
| `mode(list)` | most common value |
| `variance(list)` | sample variance |
| `stdev(list)` | sample standard deviation |
| `correlation(xs, ys)` | Pearson r |
| `normalize(list)` | scales numbers to 0..1 |
| `zscore(list)` | (x - mean) / stdev |
| `linear_fit(xs, ys)` | -> {slope, intercept, r2} straight line |
| `train(kind, X, y, ...)` | kind: 'linear', 'logistic', 'knn' -> model map |
| `predict(model, x)` | prediction for one example (a number or a list of features) |
| `probability(model, x)` | chance of class 1 for a logistic model |
| `accuracy(model, X, y)` | fraction correct (classifiers)  |
| `error(model, X, y)` | mean absolute error (regression) |
| `split_data(X, y, test=0.25, seed=1)` | -> {X_train, y_train, X_test, y_test} |
| `cluster(points, k, seed=1)` | k-means -> {labels, centers} |

### AI

| Function | What it does |
|---|---|
| `ai_setup(provider, key, model=nothing, url=nothing)` | saves your AI key on this device |
| `ai_status()` | shows which AI is set up (never shows the key) |
| `ai(question)` | asks your AI and returns its answer as text |
| `ai_code(task)` | asks the AI to write Echo code for a task (returns the code as text) |
| `ai_explain(text)` | explains code, a sequence or a result in simple words |
