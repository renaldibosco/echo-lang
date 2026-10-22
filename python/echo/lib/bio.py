"""Biology library: DNA, RNA, protein, primers, PCR, enzymes, alignment, FASTA, gels."""
import math
import random as _random
import re

from ..errors import EchoRuntimeError
from ..values import show
from . import builtin, constant

B = "bio"

IUPAC = {
    "A": "A", "C": "C", "G": "G", "T": "T", "U": "T", "R": "AG", "Y": "CT", "S": "CG", "W": "AT",
    "K": "GT", "M": "AC", "B": "CGT", "D": "AGT", "H": "ACT", "V": "ACG", "N": "ACGT",
}
COMP = str.maketrans("ACGTUNRYSWKMBDHVacgtunryswkmbdhv", "TGCAANYRSWMKVHDBtgcaanyrswmkvhdb")

CODONS = {}
_bases = "TCAG"
_aas = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
_i = 0
for _a in _bases:
    for _b in _bases:
        for _c in _bases:
            CODONS[_a + _b + _c] = _aas[_i]
            _i += 1

AA_NAMES = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "E": "Glu", "Q": "Gln", "G": "Gly",
    "H": "His", "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser",
    "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val", "*": "Stop",
}


def seq_of(s, fname="", allow_n=True):
    """Clean a DNA text: drop FASTA headers, spaces and numbers; upper case; U -> T."""
    if isinstance(s, dict) and "seq" in s:
        s = s["seq"]
    if not isinstance(s, str):
        raise EchoRuntimeError("%s needs a DNA sequence as text." % (fname + "()" if fname else "This"))
    lines = [l for l in s.splitlines() if not l.startswith(">")]
    s = re.sub(r"[\s\d]", "", "".join(lines)).upper().replace("U", "T")
    bad = set(s) - set(IUPAC)
    if bad:
        raise EchoRuntimeError("%s: '%s' is not a DNA letter." % (fname or "sequence", sorted(bad)[0]),
                               hint="Use A, C, G, T (or IUPAC codes like N, R, Y).")
    return s


def prot_of(p, fname=""):
    if isinstance(p, dict) and "protein" in p:
        p = p["protein"]
    p = re.sub(r"[\s\d*]", "", show(p)).upper()
    bad = set(p) - set("ACDEFGHIKLMNPQRSTVWYUO")
    if bad:
        raise EchoRuntimeError("%s: '%s' is not an amino-acid letter." % (fname or "protein", sorted(bad)[0]))
    return p


# ---------------- basic sequence ----------------
@builtin("dna", B, "dna(text) cleans a sequence: upper case, no spaces, numbers or FASTA header")
def _dna(s):
    return seq_of(s, "dna")


@builtin("is_dna", B, "is_dna(text) true if only A C G T (N allowed)")
def _is_dna(s):
    return isinstance(s, str) and bool(s) and all(c in "ACGTNacgtn" for c in re.sub(r"\s", "", s))


@builtin("gc", B, "gc(seq) GC content in % (2 decimals)", aliases=("gc_content",))
def gc(s):
    s = seq_of(s, "gc")
    if not s:
        return 0
    n = sum(1 for c in s if c in "GCS")
    return round(100.0 * n / len(s), 2)


@builtin("at", B, "at(seq) AT content in %", aliases=("at_content",))
def _at(s):
    s = seq_of(s, "at")
    if not s:
        return 0
    return round(100.0 * sum(1 for c in s if c in "ATW") / len(s), 2)


@builtin("gc_count", B, "gc_count(seq) how many G and C bases")
def _gc_count(s):
    return sum(1 for c in seq_of(s, "gc_count") if c in "GC")


@builtin("base_counts", B, "base_counts(seq) map of A, C, G, T counts", aliases=("count_bases",))
def _base_counts(s):
    s = seq_of(s, "base_counts")
    out = {b: s.count(b) for b in "ACGT"}
    other = len(s) - sum(out.values())
    if other:
        out["other"] = other
    return out


@builtin("complement", B, "complement(seq)")
def complement(s):
    return seq_of(s, "complement").translate(COMP)


@builtin("reverse_complement", B, "reverse_complement(seq) the other strand, read 5'->3'", aliases=("revcomp",))
def revcomp(s):
    return complement(s)[::-1]


@builtin("transcribe", B, "transcribe(dna) -> mRNA (T becomes U)")
def _transcribe(s):
    return seq_of(s, "transcribe").replace("T", "U")


@builtin("back_transcribe", B, "back_transcribe(rna) -> DNA")
def _back(s):
    return seq_of(s, "back_transcribe")


@builtin("translate", B, "translate(seq, frame=1, to_stop=false) -> protein (* = stop)")
def translate(s, frame=1, to_stop=False):
    s = seq_of(s, "translate")
    frame = int(frame)
    if frame < 0:
        s, frame = revcomp(s), -frame
    if frame not in (1, 2, 3):
        raise EchoRuntimeError("frame must be 1, 2 or 3 (or -1, -2, -3 for the other strand).")
    out = []
    for i in range(frame - 1, len(s) - 2, 3):
        aa = CODONS.get(s[i:i + 3], "X")
        if aa == "*" and to_stop:
            break
        out.append(aa)
    return "".join(out)


@builtin("codon_table", B, "codon_table() map of codon -> amino acid")
def _codon_table():
    return dict(CODONS)


@builtin("amino_name", B, "amino_name('M') -> Met")
def _amino_name(a):
    return AA_NAMES.get(show(a).upper(), "?")


@builtin("codon_usage", B, "codon_usage(seq) map codon -> count (frame 1)")
def _codon_usage(s):
    s = seq_of(s, "codon_usage")
    out = {}
    for i in range(0, len(s) - 2, 3):
        c = s[i:i + 3]
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


@builtin("find_orfs", B, "find_orfs(seq, min_aa=30) open reading frames on both strands (positions 1-based)")
def find_orfs(s, min_aa=30):
    s = seq_of(s, "find_orfs")
    n = len(s)
    found = []
    for strand, seq in (("+", s), ("-", revcomp(s))):
        for frame in range(3):
            i = frame
            while i <= len(seq) - 3:
                if seq[i:i + 3] == "ATG":
                    j = i
                    while j <= len(seq) - 3 and CODONS.get(seq[j:j + 3]) != "*":
                        j += 3
                    if j <= len(seq) - 3:
                        prot = translate(seq[i:j + 3])[:-1]
                        if len(prot) >= int(min_aa):
                            if strand == "+":
                                start, end = i + 1, j + 3
                            else:
                                start, end = n - (j + 3) + 1, n - i
                            found.append({"strand": strand, "frame": frame + 1, "start": start, "end": end,
                                          "length_bp": j + 3 - i, "protein": prot})
                        i = j + 3
                        continue
                i += 3
    found.sort(key=lambda o: -o["length_bp"])
    return found


@builtin("find_motif", B, "find_motif(seq, motif) 1-based positions; motif may use IUPAC codes like N, R, Y")
def find_motif(s, motif):
    s = seq_of(s, "find_motif")
    m = seq_of(motif, "find_motif")
    pattern = "".join("[%s]" % IUPAC[c] if len(IUPAC[c]) > 1 else c for c in m)
    return [x.start() + 1 for x in re.finditer("(?=%s)" % pattern, s)]


@builtin("hamming", B, "hamming(a, b) number of differences between two equal-length sequences")
def _hamming(a, b):
    a, b = seq_of(a, "hamming"), seq_of(b, "hamming")
    if len(a) != len(b):
        raise EchoRuntimeError("hamming() needs sequences of the same length (%d vs %d)." % (len(a), len(b)))
    return sum(1 for x, y in zip(a, b) if x != y)


@builtin("mutate", B, "mutate(seq, position, base) change one base (position 1-based)")
def _mutate(s, pos, base):
    s = seq_of(s, "mutate")
    pos = int(pos)
    if not 1 <= pos <= len(s):
        raise EchoRuntimeError("Position %d is outside the sequence (1 to %d)." % (pos, len(s)))
    return s[:pos - 1] + seq_of(base, "mutate") + s[pos:]


@builtin("random_dna", B, "random_dna(length, gc=50) random sequence")
def _random_dna(n, gc_pct=50):
    p = float(gc_pct) / 200.0
    return "".join(_random.choices("GCAT", weights=[p, p, 0.5 - p, 0.5 - p], k=int(n)))


# ---------------- melting temperature and primers ----------------
NN = {
    "AA/TT": (-7.9, -22.2), "AT/TA": (-7.2, -20.4), "TA/AT": (-7.2, -21.3), "CA/GT": (-8.5, -22.7),
    "GT/CA": (-8.4, -22.4), "CT/GA": (-7.8, -21.0), "GA/CT": (-8.2, -22.2), "CG/GC": (-10.6, -27.2),
    "GC/CG": (-9.8, -24.4), "GG/CC": (-8.0, -19.9),
}


def tm_nn(s, na=50.0, primer_nm=25.0):
    s = seq_of(s, "tm").replace("N", "")
    if len(s) < 2:
        raise EchoRuntimeError("tm() needs at least 2 bases.")
    for c in s:
        if c not in "ACGT":
            # degenerate base: use the middle of weakest and strongest
            lo = "".join(IUPAC[c][0] if len(IUPAC[c]) == 1 else ("A" if "A" in IUPAC[c] else "T" if "T" in IUPAC[c] else IUPAC[c][0]) for c in s)
            hi = "".join(IUPAC[c][0] if len(IUPAC[c]) == 1 else ("G" if "G" in IUPAC[c] else "C" if "C" in IUPAC[c] else IUPAC[c][0]) for c in s)
            return (tm_nn(lo, na, primer_nm) + tm_nn(hi, na, primer_nm)) / 2
    c = s.translate(COMP)
    dh = ds = 0.0
    for end in (s[0], s[-1]):
        if end in "AT":
            dh += 2.3
            ds += 4.1
        else:
            dh += 0.1
            ds += -2.8
    for i in range(len(s) - 1):
        key = s[i:i + 2] + "/" + c[i:i + 2]
        v = NN.get(key) or NN[key[::-1]]
        dh += v[0]
        ds += v[1]
    k = (primer_nm - primer_nm / 2) * 1e-9
    ds += 0.368 * (len(s) - 1) * math.log(na * 1e-3)
    return (1000 * dh) / (ds + 1.987 * math.log(k)) - 273.15


@builtin("tm", B, "tm(primer, na=50, primer_nm=25) melting temperature in °C (nearest-neighbour)")
def _tm(s, na=50, primer_nm=25):
    return round(tm_nn(s, float(na), float(primer_nm)), 2)


@builtin("tm_basic", B, "tm_basic(primer) Wallace rule 2(A+T) + 4(G+C)")
def _tm_basic(s):
    s = seq_of(s, "tm_basic")
    return 2 * sum(1 for c in s if c in "AT") + 4 * sum(1 for c in s if c in "GC")


def _pairs(a, b):
    return b == {"A": "T", "T": "A", "G": "C", "C": "G"}.get(a)


def _dimer(a, b):
    """Longest complementary run between a and b (b reversed under a), and whether it touches a 3' end."""
    best, at3 = 0, False
    br = b[::-1]
    for shift in range(-len(br) + 1, len(a)):
        run = 0
        for i in range(len(a) + 1):
            j = i - shift
            ok = i < len(a) and 0 <= j < len(br) and _pairs(a[i], br[j])
            if ok:
                run += 1
            elif run:
                end_i, start_j = i - 1, (i - run) - shift
                touches = end_i >= len(a) - 2 or start_j <= 1
                if run > best or (run == best and touches and not at3):
                    best, at3 = run, touches
                run = 0
    return best, at3


def _hairpin(s):
    best = 0
    for i in range(len(s)):
        for j in range(len(s) - 1, i + 3, -1):
            k = 0
            while i + k < j - k - 3 and _pairs(s[i + k], s[j - k]):
                k += 1
            best = max(best, k)
    return best


def _longest_run(s):
    best = cur = 1 if s else 0
    for i in range(1, len(s)):
        cur = cur + 1 if s[i] == s[i - 1] else 1
        best = max(best, cur)
    return best


def primer_problems(p, tm_min=52, tm_max=65, gc_min=40, gc_max=60):
    out = []
    g, t = gc(p), tm_nn(p)
    if len(p) < 18 or len(p) > 30:
        out.append("length %d nt (18-30 is usual)" % len(p))
    if g < gc_min or g > gc_max:
        out.append("GC %.0f%% (aim %d-%d%%)" % (g, gc_min, gc_max))
    if t < tm_min or t > tm_max:
        out.append("Tm %.1f °C (aim %d-%d)" % (t, tm_min, tm_max))
    if p[-1] not in "GC":
        out.append("no G/C clamp at the 3' end")
    if sum(1 for c in p[-5:] if c in "GC") > 3:
        out.append("more than 3 G/C in the last 5 bases")
    if _longest_run(p) >= 4:
        out.append("a run of 4 or more of the same base")
    if _hairpin(p) >= 4:
        out.append("possible hairpin")
    run, at3 = _dimer(p, p)
    if run >= 4 and at3:
        out.append("self-dimer at the 3' end")
    return out


@builtin("primer_check", B, "primer_check(primer) list of problems (empty list = good primer)")
def _primer_check(p):
    return primer_problems(seq_of(p, "primer_check"))


@builtin("primer_info", B, "primer_info(primer) map: length, gc, gc_count, tm, problems")
def _primer_info(p):
    p = seq_of(p, "primer_info")
    return {"seq": p, "length": len(p), "gc": gc(p), "gc_count": sum(1 for c in p if c in "GC"),
            "tm": round(tm_nn(p), 2), "problems": primer_problems(p)}


def _score(p, tm_opt, gc_min, gc_max):
    g, t = gc(p), tm_nn(p)
    s = abs(t - tm_opt)
    if g < gc_min:
        s += 10 + gc_min - g
    elif g > gc_max:
        s += 10 + g - gc_max
    if p[-1] not in "GC":
        s += 2
    if sum(1 for c in p[-5:] if c in "GC") > 3:
        s += 4
    return s, g, t


@builtin("design_primers", B,
         "design_primers(seq, product_min=100, product_max=1000, tm_opt=60, gc_min=40, gc_max=60) best primer pair")
def design_primers(s, product_min=100, product_max=1000, tm_opt=60, gc_min=40, gc_max=60):
    s = seq_of(s, "design_primers")
    if len(s) < 60:
        raise EchoRuntimeError("design_primers() needs at least 60 bases.")
    product_min, product_max = int(product_min), int(product_max)
    if product_min > len(s):
        raise EchoRuntimeError("The sequence (%d bp) is shorter than product_min (%d)." % (len(s), product_min))

    def scan(forward):
        cands = []
        for st in range(len(s)):
            for L in range(18, 26):
                if st + L > len(s):
                    break
                top = s[st:st + L]
                p = top if forward else revcomp(top)
                if "N" in p:
                    continue
                sc, g, t = _score(p, tm_opt, gc_min, gc_max)
                cands.append((sc, st, L, p, g, t))
        cands.sort()
        short = []
        for c in cands[:300]:
            sc, st, L, p, g, t = c
            if _longest_run(p) >= 4:
                sc += 6
            if _hairpin(p) >= 4:
                sc += 5
            r, a3 = _dimer(p, p)
            if r >= 4 and a3:
                sc += 6
            short.append((sc, st, L, p, g, t))
        short.sort()
        return short[:80]

    fs, rs = scan(True), scan(False)
    best = None
    for f in fs:
        for r in rs:
            size = r[1] + r[2] - f[1]
            if r[1] < f[1] + f[2] or size < product_min or size > product_max:
                continue
            d = abs(f[5] - r[5])
            run, at3 = _dimer(f[3], r[3])
            sc = f[0] + r[0] + d * 1.5 + (10 if d > 3 else 0) + (8 if run >= 4 and at3 else 0)
            if best is None or sc < best[0]:
                best = (sc, f, r, size)
    if best is None:
        raise EchoRuntimeError("No primer pair fits. Try a wider product size.")
    _, f, r, size = best
    return {"forward": f[3], "reverse": r[3], "product": size,
            "forward_start": f[1] + 1, "reverse_end": r[1] + r[2],
            "tm_forward": round(f[5], 2), "tm_reverse": round(r[5], 2),
            "gc_forward": f[4], "gc_reverse": r[4],
            "problems": primer_problems(f[3]) + ["reverse: " + x for x in primer_problems(r[3])]}


@builtin("pcr_program", B, "pcr_program(forward, reverse, product_bp, polymerase='taq') text table")
def _pcr_program(f, r, product_bp, polymerase="taq"):
    low = min(tm_nn(f), tm_nn(r))
    hifi = show(polymerase).lower() in ("hifi", "phusion", "q5", "high-fidelity")
    ta = round(min(low + 3, 72) if hifi else low - 5)
    rate = 30 if hifi else 60
    ext = max(15, int(math.ceil(int(product_bp) / 1000.0 * rate / 5.0) * 5))
    ext_t = "%d s" % ext if ext < 60 else "%d min %s" % (ext // 60, ("%d s" % (ext % 60)) if ext % 60 else "")
    rows = [
        ("Initial denaturation", "98 °C" if hifi else "95 °C", "30 s" if hifi else "3 min", "1"),
        ("Denaturation", "98 °C" if hifi else "95 °C", "10 s" if hifi else "30 s", "30-35"),
        ("Annealing", "%d °C" % ta, "20 s" if hifi else "30 s", ""),
        ("Extension", "72 °C", ext_t.strip(), ""),
        ("Final extension", "72 °C", "2 min" if hifi else "5 min", "1"),
        ("Hold", "4 °C", "forever", ""),
    ]
    lines = ["%-22s %-7s %-10s %s" % ("Step", "Temp", "Time", "Cycles")]
    lines += ["%-22s %-7s %-10s %s" % row for row in rows]
    return "\n".join(lines)


# ---------------- enzymes ----------------
# name: (site, cut position after this many bases of the site on the top strand)
ENZYMES = {
    "EcoRI": ("GAATTC", 1), "BamHI": ("GGATCC", 1), "HindIII": ("AAGCTT", 1), "XhoI": ("CTCGAG", 1),
    "NdeI": ("CATATG", 2), "NcoI": ("CCATGG", 1), "XbaI": ("TCTAGA", 1), "SalI": ("GTCGAC", 1),
    "KpnI": ("GGTACC", 5), "SacI": ("GAGCTC", 5), "PstI": ("CTGCAG", 5), "SmaI": ("CCCGGG", 3),
    "NotI": ("GCGGCCGC", 2), "NheI": ("GCTAGC", 1), "SpeI": ("ACTAGT", 1), "BglII": ("AGATCT", 1),
    "EcoRV": ("GATATC", 3), "ClaI": ("ATCGAT", 2), "SphI": ("GCATGC", 5), "ApaI": ("GGGCCC", 5),
    "HaeIII": ("GGCC", 2), "AluI": ("AGCT", 2), "MspI": ("CCGG", 1), "TaqI": ("TCGA", 1),
    "DpnII": ("GATC", 0), "Sau3AI": ("GATC", 0),
}


@builtin("enzymes", B, "enzymes() list of known restriction enzymes")
def _enzymes():
    return sorted(ENZYMES)


@builtin("restriction_sites", B, "restriction_sites(seq) map enzyme -> cut positions (only enzymes that cut)")
def restriction_sites(s, enzyme_list=None):
    s = seq_of(s, "restriction_sites")
    names = enzyme_list or list(ENZYMES)
    if isinstance(names, str):
        names = [names]
    out = {}
    for name in names:
        if name not in ENZYMES:
            raise EchoRuntimeError("Unknown enzyme '%s'." % name, hint="See enzymes()")
        site, cut = ENZYMES[name]
        pos = [m.start() + cut for m in re.finditer("(?=%s)" % site, s)]
        if pos:
            out[name] = pos
    return out


@builtin("digest", B, "digest(seq, enzyme or list, circular=false) fragment sizes, largest first")
def _digest(s, enz, circular=False):
    s = seq_of(s, "digest")
    names = [enz] if isinstance(enz, str) else list(enz)
    cuts = sorted(set(p for v in restriction_sites(s, names).values() for p in v))
    if not cuts:
        return [len(s)]
    if circular:
        frags = [b - a for a, b in zip(cuts, cuts[1:])] + [len(s) - cuts[-1] + cuts[0]]
    else:
        edges = [0] + cuts + [len(s)]
        frags = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0]
    return sorted(frags, reverse=True)


# ---------------- alignment ----------------
@builtin("align", B, "align(a, b, match=1, mismatch=-1, gap=-2) global alignment map")
def _align(a, b, match=1, mismatch=-1, gap=-2):
    a, b = show(a).upper(), show(b).upper()
    if len(a) * len(b) > 4_000_000:
        raise EchoRuntimeError("align() sequences are too long (keep the product under 4 million).")
    n, m = len(a), len(b)
    score = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = i * gap
    for j in range(1, m + 1):
        score[0][j] = j * gap
    for i in range(1, n + 1):
        ai = a[i - 1]
        row, prev = score[i], score[i - 1]
        for j in range(1, m + 1):
            d = prev[j - 1] + (match if ai == b[j - 1] else mismatch)
            u = prev[j] + gap
            l = row[j - 1] + gap
            row[j] = d if d >= u and d >= l else (u if u >= l else l)
    top, bot, mid = [], [], []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and score[i][j] == score[i - 1][j - 1] + (match if a[i - 1] == b[j - 1] else mismatch):
            top.append(a[i - 1])
            bot.append(b[j - 1])
            mid.append("|" if a[i - 1] == b[j - 1] else ".")
            i, j = i - 1, j - 1
        elif i > 0 and score[i][j] == score[i - 1][j] + gap:
            top.append(a[i - 1])
            bot.append("-")
            mid.append(" ")
            i -= 1
        else:
            top.append("-")
            bot.append(b[j - 1])
            mid.append(" ")
            j -= 1
    top, mid, bot = "".join(reversed(top)), "".join(reversed(mid)), "".join(reversed(bot))
    same = mid.count("|")
    return {"score": score[n][m], "a": top, "match": mid, "b": bot,
            "identity": round(100.0 * same / max(1, len(mid)), 2), "length": len(mid)}


# ---------------- protein ----------------
AA_WEIGHT = {
    "A": 89.0932, "C": 121.1582, "D": 133.1027, "E": 147.1293, "F": 165.1891, "G": 75.0666,
    "H": 155.1546, "I": 131.1729, "K": 146.1876, "L": 131.1729, "M": 149.2113, "N": 132.1179,
    "O": 255.3134, "P": 115.1305, "Q": 146.1445, "R": 174.201, "S": 105.0926, "T": 119.1192,
    "U": 168.0532, "V": 117.1463, "W": 204.2252, "Y": 181.1885,
}
WATER = 18.0153
KD = {"A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2,
      "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9,
      "Y": -1.3, "V": 4.2}
POS_PK = {"Nterm": 7.5, "K": 10.0, "R": 12.0, "H": 5.98}
NEG_PK = {"Cterm": 3.55, "D": 4.05, "E": 4.45, "C": 9.0, "Y": 10.0}
PK_CTERM = {"D": 4.55, "E": 4.75}
PK_NTERM = {"A": 7.59, "M": 7.0, "S": 6.93, "P": 8.36, "T": 6.82, "V": 7.44, "E": 7.7}


@builtin("protein_mass", B, "protein_mass(protein) average mass in Da")
def protein_mass(p):
    p = prot_of(p, "protein_mass")
    if not p:
        return 0
    return round(sum(AA_WEIGHT[a] for a in p) - WATER * (len(p) - 1), 4)


def _charge(p, ph):
    pos = dict(POS_PK)
    neg = dict(NEG_PK)
    if p[0] in PK_NTERM:
        pos["Nterm"] = PK_NTERM[p[0]]
    if p[-1] in PK_CTERM:
        neg["Cterm"] = PK_CTERM[p[-1]]
    counts = {a: p.count(a) for a in "KRHDECY"}
    counts["Nterm"] = counts["Cterm"] = 1
    pc = sum(counts[a] * (10 ** pk) / (10 ** pk + 10 ** ph) for a, pk in pos.items())
    nc = sum(counts[a] * (10 ** ph) / (10 ** pk + 10 ** ph) for a, pk in neg.items())
    return pc - nc


@builtin("isoelectric_point", B, "isoelectric_point(protein) pI", aliases=("pi_of",))
def isoelectric_point(p):
    p = prot_of(p, "isoelectric_point")
    lo, hi = 4.05, 12.0
    ph = 7.775
    ch = _charge(p, ph)
    if ch > 0:
        lo = ph
        while _charge(p, hi) > 0:
            hi += 2
    else:
        hi = ph
        while _charge(p, lo) < 0:
            lo -= 2
    while hi - lo > 0.0001:
        mid = (lo + hi) / 2
        if _charge(p, mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


@builtin("charge_at", B, "charge_at(protein, ph=7) net charge")
def _charge_at(p, ph=7.0):
    return round(_charge(prot_of(p, "charge_at"), float(ph)), 3)


@builtin("gravy", B, "gravy(protein) hydropathy (Kyte-Doolittle average); above 0 = water-repelling")
def _gravy(p):
    p = prot_of(p, "gravy")
    vals = [KD[a] for a in p if a in KD]
    return round(sum(vals) / len(vals), 4) if vals else 0


@builtin("protein_info", B, "protein_info(protein) map: length, mass, pi, gravy, charge_7")
def _protein_info(p):
    p = prot_of(p, "protein_info")
    return {"protein": p, "length": len(p), "mass": protein_mass(p), "pi": isoelectric_point(p),
            "gravy": _gravy(p), "charge_7": _charge_at(p, 7.0)}


# ---------------- DNA mass, lab maths ----------------
@builtin("dna_mass", B, "dna_mass(seq, double=false) mass in g/mol (single strand unless double=true)")
def _dna_mass(s, double=False):
    s = seq_of(s, "dna_mass")
    w = {"A": 313.21, "C": 289.18, "G": 329.21, "T": 304.2}
    single = sum(w.get(c, 308.95) for c in s) - 61.96
    if double:
        single += sum(w.get(c, 308.95) for c in revcomp(s)) - 61.96
    return round(single, 2)


@builtin("dilute", B, "dilute(c1, c2, v2) volume of stock to take (C1V1 = C2V2)")
def _dilute(c1, c2, v2):
    if c1 == 0:
        raise EchoRuntimeError("Stock concentration can't be 0.")
    return round(c2 * v2 / c1, 4)


@builtin("copy_number", B, "copy_number(ng, length_bp) copies of double-stranded DNA")
def _copy_number(ng, bp):
    return round(ng * 6.022e23 / (bp * 650 * 1e9))


@builtin("molarity", B, "molarity(mass_g, mol_weight, volume_l) in mol/L")
def _molarity(mass, mw, vol):
    return mass / mw / vol


# ---------------- FASTA ----------------
@builtin("parse_fasta", B, "parse_fasta(text) list of {name, seq}")
def parse_fasta(text):
    recs, name, buf = [], None, []
    for line in show(text).splitlines():
        line = line.strip()
        if line.startswith(">"):
            if name is not None:
                recs.append({"name": name, "seq": "".join(buf).upper()})
            name, buf = line[1:].strip(), []
        elif line:
            buf.append(re.sub(r"[\s\d]", "", line))
    if name is not None:
        recs.append({"name": name, "seq": "".join(buf).upper()})
    elif buf:
        recs.append({"name": "sequence", "seq": "".join(buf).upper()})
    return recs


@builtin("read_fasta", B, "read_fasta(path) list of {name, seq}")
def _read_fasta(path):
    with open(show(path), encoding="utf-8") as f:
        return parse_fasta(f.read())


@builtin("to_fasta", B, "to_fasta(name, seq) FASTA text (60 letters per line)")
def to_fasta(name, s):
    s = show(s)
    return ">" + show(name) + "\n" + "\n".join(s[i:i + 60] for i in range(0, len(s), 60)) + "\n"


@builtin("write_fasta", B, "write_fasta(path, records) records = list of {name, seq}")
def _write_fasta(path, recs):
    if isinstance(recs, dict):
        recs = [recs]
    with open(show(path), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(to_fasta(r["name"], r["seq"]))
    return True


# ---------------- gel ----------------
LADDER = [10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 750, 500, 250]


@builtin("gel", B, "gel(lanes, ladder=true) draws an agarose gel; lanes = list of sizes or list of lists")
def _gel(lanes, ladder=True):
    if lanes and not isinstance(lanes[0], list):
        lanes = [lanes]
    cols = ([LADDER] if ladder else []) + [list(l) for l in lanes]
    rows = 24
    lo, hi = math.log10(100), math.log10(12000)

    def row_of(bp):
        bp = min(max(bp, 100), 12000)
        return int(round((hi - math.log10(bp)) / (hi - lo) * (rows - 1)))

    names = (["Ladder"] if ladder else []) + ["Lane %d" % (i + 1) for i in range(len(lanes))]
    out = ["  " + " ".join("%-7s" % n[:7] for n in names), "  " + " ".join(["  ▔▔▔  "] * len(cols))]
    grid = [[set() for _ in cols] for _ in range(rows)]
    for c, sizes in enumerate(cols):
        for bp in sizes:
            grid[row_of(bp)][c].add(bp)
    for r in range(rows):
        cells = ["  ███  " if grid[r][c] else "       " for c in range(len(cols))]
        label = ""
        if ladder and grid[r][0]:
            label = "  %d bp" % max(grid[r][0])
        out.append("  " + " ".join(cells) + label)
    return "\n".join(out)


constant("start_codon", B, "ATG", "start_codon = ATG")
constant("stop_codons", B, ["TAA", "TAG", "TGA"], "stop_codons = TAA, TAG, TGA")
