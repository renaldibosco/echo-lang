# Moving from Echo 1 to Echo 2

Echo 2 keeps the English style but has **one way to write each thing**, built-in functions grouped into
**modules**, optional **types**, **error codes**, a **checker** and a **formatter**.

## Upgrade automatically

```
echolang upgrade my_program.echo        # show the Echo 2 version
echolang upgrade my_program.echo -w     # overwrite the file
echolang check my_program.echo          # then look at anything left
```

In the Echo Lang app, press **Check**; if the code is Echo 1, the dialog offers **Upgrade to Echo 2**.

## What changed

| Echo 1 | Echo 2 | Why |
|---|---|---|
| `x = 5` | `set x to 5` | one way to set a variable |
| `x += 1`, `set x += 1` | `set x to x + 1` | |
| `if x > 3` (no `then`) | `if x > 3 then` | `then` is required |
| `end if`, `end for` | `end` | |
| `for x in items` | `for each x in items` | |
| `stop`, `skip`, `pass` | `break`, `continue`, (empty block) | |
| `repeat forever` | `while true` | |
| `yes`, `no` | `true`, `false` | |
| `x is 3`, `x is not 3` | `x == 3`, `x != 3` | |
| `'text'` | `"text"` | double quotes only |
| `say 1; say 2` | two lines | one statement per line |
| `length of seq` | `length(seq)` | one way to call a function |
| `seq.gc()`, `"atg".upper()` | `bio.gc(seq)`, `upper("atg")` | no method calls on values |
| `gc(seq)`, `translate(seq)` ... | `bio.gc(seq)`, `bio.translate(seq)` | functions live in modules |
| `round`, `sqrt`, `pi` | `math.round`, `math.sqrt`, `math.pi` | |
| `random()`, `random_int(a, b)` | `random.number()`, `random.integer(a, b)` | |
| `mean`, `stdev`, `linear_fit` | `stats.mean`, `stats.stdev`, `stats.linear_fit` | |
| `train`, `predict`, `cluster` | `ml.train`, `ml.predict`, `ml.cluster` | |
| `sha256`, `caesar` | `cyber.sha256`, `cyber.caesar` | |
| `truth_table`, `to_binary` | `gates.truth_table`, `gates.to_binary` | |
| `read_file`, `write_file`, `file_exists` | `file.read`, `file.write`, `file.exists` | |
| `from_json`, `to_json` | `json.parse`, `json.format` | |
| `now()`, `wait(s)` | `time.now()`, `time.wait(s)` | |
| `ai(q)`, `ai_code`, `ai_explain`, `ai_setup` | `ai.ask(q)`, `ai.code`, `ai.explain`, `ai.setup` | |
| `ask ai "q" into a` | `set a to ai.ask("q")` | |
| `print(...)`, `input(...)` | `say ...`, `ask ... into name` | |
| `int(x)`, `bool(x)` | `integer(x)`, `boolean(x)` | |
| `len`, `size`, `revcomp`, `average`, `sd` ... | `length`, `bio.reverse_complement`, `stats.mean`, `stats.stdev` | one name per function |
| `use bio` | (nothing: modules are always there) | |
| functions from `use "helpers.echo"` were global | `helpers.function(...)` | files are modules |
| `catch problem` gave text | `problem` is an `Error` record: `problem.message`, `problem.code`, `problem.line` | |
| `type(true)` was `"yes/no"` | `"boolean"` | |

## Behaviour that is stricter now

These can't always be fixed automatically; `echolang check` and the error codes point to them.

- **Conditions must be true or false (E303).** `if items then` becomes `if length(items) > 0 then`.
- **Gates need matching sides (E301).** `true and 1` is an error; use two booleans or two bits.
- **`add ... to` is for lists (E301).** For numbers write `set total to total + value`.
- **`in` on text is exact.** `"atg" in "ATGC"` is now `false`; clean sequences with `bio.dna()` first.
- **Records have fixed fields (E202)** and fields without a default must be given (E205).
- **Record names start with a capital letter.**
- **`filter` needs a function that returns true or false.**
