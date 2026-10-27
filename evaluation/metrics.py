def precision_at_k(retrieved, relevant, k):
    if k < 1:
        raise ValueError("k must be positive")
    return len(set(retrieved[:k]) & set(relevant)) / k


def recall_at_k(retrieved, relevant, k):
    relevant = set(relevant)
    return len(set(retrieved[:k]) & relevant) / len(relevant) if relevant else None


def reciprocal_rank(retrieved, relevant):
    relevant = set(relevant)
    if not relevant:
        return None
    return next((1.0 / rank for rank, item in enumerate(retrieved, 1) if item in relevant), 0.0)


def mean_measured(values):
    import math
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return sum(values) / len(values) if values else None

