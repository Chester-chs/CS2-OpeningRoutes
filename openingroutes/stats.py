"""Small, dependency-free (NumPy only) statistics used by the formation analysis.

Implementations follow scikit-learn / SciPy definitions and are checked against
them in the test suite, so the desktop package does not need either library.
"""

import math

import numpy as np


def kmeans(x: np.ndarray, k: int, *, n_init: int = 20, seed: int = 42, max_iter: int = 300):
    """Lloyd's algorithm with k-means++ seeding; returns (labels, centers, inertia)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if not 1 <= k <= n:
        raise ValueError("k must be between 1 and the number of samples")
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        centers = [x[rng.integers(n)]]
        for _ in range(1, k):
            d2 = np.min(((x[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
            total = d2.sum()
            centers.append(x[rng.integers(n)] if total == 0 else x[rng.choice(n, p=d2 / total)])
        centers = np.array(centers)
        labels = np.zeros(n, dtype=int)
        for _ in range(max_iter):
            dist = ((x[:, None, :] - centers[None]) ** 2).sum(-1)
            new = dist.argmin(1)
            moved = []
            for j in range(k):
                members = x[new == j]
                if len(members):
                    moved.append(members.mean(0))
                else:  # re-seed an empty cluster with the farthest point
                    far = dist.min(1).argmax()
                    new[far] = j
                    moved.append(x[far])
            moved = np.array(moved)
            converged = np.array_equal(new, labels) and np.allclose(moved, centers)
            labels, centers = new, moved
            if converged:
                break
        inertia = float(((x - centers[labels]) ** 2).sum())
        if best is None or inertia < best[2] - 1e-12:
            best = (labels.copy(), centers.copy(), inertia)
    return best


def _pairwise(x):
    sq = (x**2).sum(1)
    return np.sqrt(np.maximum(sq[:, None] + sq[None] - 2 * x @ x.T, 0))


def silhouette(x, labels) -> float:
    x, labels = np.asarray(x, float), np.asarray(labels)
    ids = np.unique(labels)
    if not 2 <= len(ids) <= len(x) - 1:
        raise ValueError("silhouette needs 2..n-1 clusters")
    d = _pairwise(x)
    scores = np.zeros(len(x))
    for i in range(len(x)):
        own = labels == labels[i]
        if own.sum() == 1:
            continue
        a = d[i, own].sum() / (own.sum() - 1)
        b = min(d[i, labels == c].mean() for c in ids if c != labels[i])
        scores[i] = 0 if max(a, b) == 0 else (b - a) / max(a, b)
    return float(scores.mean())


def davies_bouldin(x, labels) -> float:
    x, labels = np.asarray(x, float), np.asarray(labels)
    ids = np.unique(labels)
    cent = np.array([x[labels == c].mean(0) for c in ids])
    spread = np.array([np.linalg.norm(x[labels == c] - cent[i], axis=1).mean() for i, c in enumerate(ids)])
    sep = _pairwise(cent)
    ratios = []
    for i in range(len(ids)):
        ratios.append(
            max((spread[i] + spread[j]) / sep[i, j] for j in range(len(ids)) if j != i and sep[i, j] > 0)
        )
    return float(np.mean(ratios))


def calinski_harabasz(x, labels) -> float:
    x, labels = np.asarray(x, float), np.asarray(labels)
    ids = np.unique(labels)
    n, k = len(x), len(ids)
    mean = x.mean(0)
    between = sum((labels == c).sum() * ((x[labels == c].mean(0) - mean) ** 2).sum() for c in ids)
    within = sum(((x[labels == c] - x[labels == c].mean(0)) ** 2).sum() for c in ids)
    return float("inf") if within == 0 else float(between * (n - k) / (within * (k - 1)))


def dense_rank(values, *, descending: bool):
    order = sorted(set(values), reverse=descending)
    return [order.index(v) + 1 for v in values]


def select_k(x, ks, *, seed: int = 42, min_size: int = 1):
    """TAGNet's rule: mean dense rank of silhouette (desc), Davies-Bouldin (asc) and
    Calinski-Harabasz (desc) over the candidates. Candidates with a cluster smaller
    than ``min_size`` are reported but not eligible."""
    rows = []
    for k in ks:
        if k < 2 or k >= len(x):
            continue
        labels, _, inertia = kmeans(x, k, seed=seed)
        if len(np.unique(labels)) < 2:
            continue
        rows.append(
            {
                "k": k,
                "silhouette": silhouette(x, labels),
                "davies_bouldin": davies_bouldin(x, labels),
                "calinski_harabasz": calinski_harabasz(x, labels),
                "min_size": int(np.bincount(labels).min()),
                "inertia": inertia,
                "labels": labels,
            }
        )
    if not rows:
        return None, []
    for key, desc in (("silhouette", True), ("davies_bouldin", False), ("calinski_harabasz", True)):
        for row, rank in zip(rows, dense_rank([r[key] for r in rows], descending=desc), strict=True):
            row[f"rank_{key}"] = rank
    for row in rows:
        row["mean_rank"] = (
            row["rank_silhouette"] + row["rank_davies_bouldin"] + row["rank_calinski_harabasz"]
        ) / 3
        row["eligible"] = row["min_size"] >= min_size
    eligible = [r for r in rows if r["eligible"]] or rows
    best = min(eligible, key=lambda r: (r["mean_rank"], r["k"]))
    return best, rows


def adjusted_rand(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    _, ai = np.unique(a, return_inverse=True)
    _, bi = np.unique(b, return_inverse=True)
    table = np.zeros((ai.max() + 1, bi.max() + 1))
    np.add.at(table, (ai, bi), 1)

    def comb2(v):
        return (v * (v - 1) / 2).sum()

    index, rows, cols = comb2(table), comb2(table.sum(1)), comb2(table.sum(0))
    expected = rows * cols / comb2(np.array([len(a)]))
    maximum = (rows + cols) / 2
    return 1.0 if maximum == expected else float((index - expected) / (maximum - expected))


def _gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) (Numerical Recipes series / continued fraction)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        ap = a
        for _ in range(1000):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1.0 - total * math.exp(-x + a * math.log(x) - gln))
    b, c, d = x + 1 - a, 1e300, 1 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_test(table) -> dict:
    """Pearson chi-square test of independence (no continuity correction, like SciPy for dof>1)."""
    t = np.asarray(table, dtype=float)
    t = t[t.sum(1) > 0][:, t.sum(0) > 0]
    if t.shape[0] < 2 or t.shape[1] < 2:
        return {
            "chi2": None,
            "dof": 0,
            "p_value": None,
            "cramers_v": None,
            "min_expected": None,
            "n": int(t.sum()),
        }
    n = t.sum()
    expected = t.sum(1, keepdims=True) * t.sum(0, keepdims=True) / n
    dof = (t.shape[0] - 1) * (t.shape[1] - 1)
    if dof == 1:  # Yates correction, as scipy.stats.chi2_contingency does by default
        diff = np.maximum(np.abs(t - expected) - 0.5, 0)
        chi2 = float((diff**2 / expected).sum())
    else:
        chi2 = float(((t - expected) ** 2 / expected).sum())
    v = math.sqrt(chi2 / (n * (min(t.shape) - 1)))
    return {
        "chi2": chi2,
        "dof": dof,
        "p_value": _gammaincc(dof / 2, chi2 / 2),
        "cramers_v": v,
        "min_expected": float(expected.min()),
        "n": int(n),
    }


def holm(p_values: list[float | None]) -> list[float | None]:
    indexed = sorted((p, i) for i, p in enumerate(p_values) if p is not None)
    m = len(indexed)
    adjusted: list[float | None] = [None] * len(p_values)
    running = 0.0
    for rank, (p, i) in enumerate(indexed):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[i] = running
    return adjusted


def cosine_similarity(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return None if na == 0 or nb == 0 else float(a @ b / (na * nb))
