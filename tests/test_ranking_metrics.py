from ml.evaluation.ranking_metrics import precision_at_k


def test_precision_at_k_perfect():
    items = [1, 2, 3, 4]
    scores = {1: 4.0, 2: 3.0, 3: 2.0, 4: 1.0}
    positives = {1, 2}
    p = precision_at_k(items, lambda i: scores[i], lambda i: i in positives, k=2)
    assert p == 1.0


def test_precision_at_k_partial():
    items = [1, 2, 3, 4]
    scores = {1: 4.0, 2: 3.0, 3: 2.0, 4: 1.0}
    positives = {1, 3}  # only 1 of top-2 by score is positive
    p = precision_at_k(items, lambda i: scores[i], lambda i: i in positives, k=2)
    assert p == 0.5


def test_precision_at_k_empty_items():
    assert precision_at_k([], lambda i: 0.0, lambda i: True, k=5) == 0.0


def test_precision_at_k_caps_to_available_items():
    items = [1, 2]
    p = precision_at_k(items, lambda i: i, lambda i: True, k=10)
    assert p == 1.0
