import numpy as np
import pytest

from openingroutes import stats

sk = pytest.importorskip("sklearn.metrics")
scipy_stats = pytest.importorskip("scipy.stats")


def blobs(seed=0):
    rng = np.random.default_rng(seed)
    centers = np.array([[0, 0], [6, 0], [0, 6], [6, 6]])
    x = np.vstack([c + rng.normal(0, 0.8, size=(30, 2)) for c in centers])
    return x, np.repeat(np.arange(4), 30)


def test_cluster_metrics_match_scikit_learn():
    x, _ = blobs()
    labels, _, _ = stats.kmeans(x, 4)
    assert stats.silhouette(x, labels) == pytest.approx(sk.silhouette_score(x, labels), rel=1e-9)
    assert stats.davies_bouldin(x, labels) == pytest.approx(sk.davies_bouldin_score(x, labels), rel=1e-9)
    assert stats.calinski_harabasz(x, labels) == pytest.approx(
        sk.calinski_harabasz_score(x, labels), rel=1e-9
    )


def test_kmeans_recovers_clear_structure_and_k_selection_picks_it():
    x, truth = blobs(1)
    labels, _, _ = stats.kmeans(x, 4)
    assert stats.adjusted_rand(truth, labels) == pytest.approx(1.0)
    best, rows = stats.select_k(x, range(2, 9))
    assert best["k"] == 4 and len(rows) == 7
    assert stats.adjusted_rand([0, 0, 1, 1], [1, 1, 0, 0]) == 1.0
    a, b = [0, 0, 1, 1, 2, 2, 0, 1], [0, 1, 1, 1, 2, 0, 0, 2]
    assert stats.adjusted_rand(a, b) == pytest.approx(sk.adjusted_rand_score(a, b))


def test_chi_square_and_holm_match_scipy():
    for table in (
        [[10, 20, 30], [20, 25, 5]],
        [[12, 3], [4, 15]],
        [[1, 0, 9, 4], [3, 5, 2, 8], [7, 7, 1, 0]],
    ):
        ours = stats.chi2_test(table)
        chi2, p, dof, _ = scipy_stats.chi2_contingency(table)
        assert ours["chi2"] == pytest.approx(chi2) and ours["dof"] == dof
        assert ours["p_value"] == pytest.approx(p, rel=1e-7, abs=1e-12)
    assert stats.chi2_test([[5, 0], [0, 0]])["p_value"] is None
    assert stats.holm([0.01, 0.04, None, 0.03]) == pytest.approx([0.03, 0.06, None, 0.06], nan_ok=True)
