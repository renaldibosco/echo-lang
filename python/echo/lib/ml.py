"""Statistics and small machine-learning models in pure Python (no installs).
Models are plain maps, so you can print them or save them with to_json."""
import math
import random as _random

from ..errors import EchoRuntimeError
from ..values import show
from . import builtin

M = "ml"


def _nums(xs, f):
    if not isinstance(xs, list) or not xs:
        raise EchoRuntimeError("%s() needs a non-empty list of numbers." % f)
    for x in xs:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise EchoRuntimeError("%s() needs numbers, found %s." % (f, show(x, True)))
    return xs


@builtin("mean", M, "mean(list) average", aliases=("average",))
def mean(xs):
    xs = _nums(xs, "mean")
    return sum(xs) / len(xs)


@builtin("median", M, "median(list)")
def _median(xs):
    xs = sorted(_nums(xs, "median"))
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


@builtin("mode", M, "mode(list) most common value")
def _mode(xs):
    if not xs:
        raise EchoRuntimeError("mode() of an empty list.")
    return max(xs, key=lambda v: (xs.count(v), -xs.index(v)))


@builtin("variance", M, "variance(list) sample variance")
def variance(xs):
    xs = _nums(xs, "variance")
    if len(xs) < 2:
        return 0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


@builtin("stdev", M, "stdev(list) sample standard deviation", aliases=("sd",))
def stdev(xs):
    return math.sqrt(variance(xs))


@builtin("correlation", M, "correlation(xs, ys) Pearson r")
def correlation(xs, ys):
    xs, ys = _nums(xs, "correlation"), _nums(ys, "correlation")
    if len(xs) != len(ys):
        raise EchoRuntimeError("correlation() needs two lists of the same length.")
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0
    return sxy / (sx * sy)


@builtin("normalize", M, "normalize(list) scales numbers to 0..1")
def _normalize(xs):
    xs = _nums(xs, "normalize")
    lo, hi = min(xs), max(xs)
    return [0 if hi == lo else (x - lo) / (hi - lo) for x in xs]


@builtin("zscore", M, "zscore(list) (x - mean) / stdev")
def _zscore(xs):
    m, s = mean(xs), stdev(xs)
    return [0 if s == 0 else (x - m) / s for x in xs]


def _rows(X, f):
    if not isinstance(X, list) or not X:
        raise EchoRuntimeError("%s() needs a list of examples." % f)
    rows = [[x] if isinstance(x, (int, float)) and not isinstance(x, bool) else list(x) for x in X]
    width = len(rows[0])
    for r in rows:
        if len(r) != width:
            raise EchoRuntimeError("%s(): every example must have the same number of features." % f)
        _nums(r, f)
    return rows


def _solve(A, b):
    """Gaussian elimination with partial pivoting."""
    n = len(A)
    M_ = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M_[r][c]))
        if abs(M_[p][c]) < 1e-12:
            raise EchoRuntimeError("The data can't fit a line (features repeat or too few examples).")
        M_[c], M_[p] = M_[p], M_[c]
        for r in range(n):
            if r != c:
                f = M_[r][c] / M_[c][c]
                for k in range(c, n + 1):
                    M_[r][k] -= f * M_[c][k]
    return [M_[i][n] / M_[i][i] for i in range(n)]


@builtin("linear_fit", M, "linear_fit(xs, ys) -> {slope, intercept, r2} straight line")
def linear_fit(xs, ys):
    xs, ys = _nums(xs, "linear_fit"), _nums(ys, "linear_fit")
    if len(xs) != len(ys) or len(xs) < 2:
        raise EchoRuntimeError("linear_fit() needs two lists of the same length (2 or more).")
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise EchoRuntimeError("linear_fit(): all x values are the same.")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1
    return {"kind": "linear", "slope": slope, "intercept": intercept, "r2": r2,
            "weights": [slope], "bias": intercept}


def _sigmoid(z):
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1 / (1 + math.exp(-z))


@builtin("train", M, "train(kind, X, y, ...) kind: 'linear', 'logistic', 'knn' -> model map")
def train(kind, X, y, k=3, epochs=2000, rate=0.1):
    kind = show(kind).lower()
    rows = _rows(X, "train")
    if not isinstance(y, list) or len(y) != len(rows):
        raise EchoRuntimeError("train(): y must be a list with one answer per example.")
    if kind == "knn":
        return {"kind": "knn", "k": int(k), "X": rows, "y": list(y)}
    _nums(y, "train")
    n, d = len(rows), len(rows[0])
    if kind == "linear":
        A = [[sum(r[i] * r[j] for r in rows) for j in range(d)] + [sum(r[i] for r in rows)] for i in range(d)]
        A.append([sum(r[j] for r in rows) for j in range(d)] + [n])
        b = [sum(r[i] * t for r, t in zip(rows, y)) for i in range(d)] + [sum(y)]
        sol = _solve(A, b)
        model = {"kind": "linear", "weights": sol[:d], "bias": sol[d]}
        preds = [predict(model, r) for r in rows]
        my = mean(y)
        ss_tot = sum((t - my) ** 2 for t in y)
        model["r2"] = 1 - sum((t - p) ** 2 for t, p in zip(y, preds)) / ss_tot if ss_tot else 1
        return model
    if kind == "logistic":
        if set(y) - {0, 1}:
            raise EchoRuntimeError("logistic needs y values of 0 or 1.")
        mu = [mean([r[j] for r in rows]) for j in range(d)]
        sd = [stdev([r[j] for r in rows]) or 1 for j in range(d)]
        Z = [[(r[j] - mu[j]) / sd[j] for j in range(d)] for r in rows]
        w, b0 = [0.0] * d, 0.0
        for _ in range(int(epochs)):
            gw, gb = [0.0] * d, 0.0
            for z, t in zip(Z, y):
                err = _sigmoid(sum(wi * zi for wi, zi in zip(w, z)) + b0) - t
                for j in range(d):
                    gw[j] += err * z[j]
                gb += err
            w = [wi - rate * g / n for wi, g in zip(w, gw)]
            b0 -= rate * gb / n
        return {"kind": "logistic", "weights": w, "bias": b0, "mean": mu, "scale": sd}
    raise EchoRuntimeError("Unknown model kind '%s'." % kind, hint="Use 'linear', 'logistic' or 'knn'.")


@builtin("predict", M, "predict(model, x) prediction for one example (a number or a list of features)")
def predict(model, x):
    if not isinstance(model, dict) or "kind" not in model:
        raise EchoRuntimeError("predict() needs a model made by train() or linear_fit().")
    row = [x] if isinstance(x, (int, float)) and not isinstance(x, bool) else list(x)
    kind = model["kind"]
    if kind == "linear":
        return sum(w * v for w, v in zip(model["weights"], row)) + model["bias"]
    if kind == "logistic":
        z = [(v - m) / s for v, m, s in zip(row, model["mean"], model["scale"])]
        p = _sigmoid(sum(w * v for w, v in zip(model["weights"], z)) + model["bias"])
        return 1 if p >= 0.5 else 0
    if kind == "knn":
        dist = sorted((math.dist(row, r), t) for r, t in zip(model["X"], model["y"]))[:model["k"]]
        votes = {}
        for _, t in dist:
            votes[t] = votes.get(t, 0) + 1
        return max(votes, key=lambda t: (votes[t], -[v for _, v in dist].index(t)))
    raise EchoRuntimeError("Unknown model kind '%s'." % kind)


@builtin("probability", M, "probability(model, x) chance of class 1 for a logistic model")
def _probability(model, x):
    if model.get("kind") != "logistic":
        raise EchoRuntimeError("probability() needs a logistic model.")
    row = [x] if isinstance(x, (int, float)) else list(x)
    z = [(v - m) / s for v, m, s in zip(row, model["mean"], model["scale"])]
    return _sigmoid(sum(w * v for w, v in zip(model["weights"], z)) + model["bias"])


@builtin("accuracy", M, "accuracy(model, X, y) fraction correct (classifiers) ")
def _accuracy(model, X, y):
    rows = _rows(X, "accuracy")
    right = sum(1 for r, t in zip(rows, y) if predict(model, r) == t)
    return right / len(rows)


@builtin("error", M, "error(model, X, y) mean absolute error (regression)")
def _error(model, X, y):
    rows = _rows(X, "error")
    return sum(abs(predict(model, r) - t) for r, t in zip(rows, y)) / len(rows)


@builtin("split_data", M, "split_data(X, y, test=0.25, seed=1) -> {X_train, y_train, X_test, y_test}")
def _split(X, y, test=0.25, seed=1):
    idx = list(range(len(X)))
    _random.Random(seed).shuffle(idx)
    cut = max(1, int(round(len(idx) * (1 - float(test)))))
    tr, te = idx[:cut], idx[cut:]
    return {"X_train": [X[i] for i in tr], "y_train": [y[i] for i in tr],
            "X_test": [X[i] for i in te], "y_test": [y[i] for i in te]}


@builtin("cluster", M, "cluster(points, k, seed=1) k-means -> {labels, centers}")
def _cluster(points, k, seed=1):
    rows = _rows(points, "cluster")
    k = int(k)
    if not 1 <= k <= len(rows):
        raise EchoRuntimeError("cluster(): k must be between 1 and the number of points.")
    rnd = _random.Random(seed)
    centers = [list(c) for c in rnd.sample(rows, k)]
    labels = [0] * len(rows)
    for _ in range(100):
        new = [min(range(k), key=lambda c: math.dist(r, centers[c])) for r in rows]
        for c in range(k):
            members = [r for r, l in zip(rows, new) if l == c]
            if members:
                centers[c] = [sum(col) / len(members) for col in zip(*members)]
        if new == labels:
            break
        labels = new
    return {"labels": labels, "centers": centers}
