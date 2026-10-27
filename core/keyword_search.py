import re

import numpy as np
from rank_bm25 import BM25Okapi


def tokenize(text):
    # Unicode words, article numbers, and section IDs retain legal references.
    return re.findall(r"\w+(?:[-']\w+)*", text.casefold())


def keyword_search(query, chunks, k):
    if not chunks:
        return []
    corpus = [tokenize(c.text) or ["__empty__"] for c in chunks]
    tokens = tokenize(query)
    if not tokens:
        return []
    # BM25Okapi's negative common-term IDF can discard genuine matches in
    # small legal corpora. A positive IDF floor retains those exact matches.
    bm25 = BM25Okapi(corpus)
    bm25.idf = {term: max(value, 0.01) for term, value in bm25.idf.items()}
    scores = bm25.get_scores(tokens)
    order = np.argsort(-scores, kind="stable")[:k]
    return [(chunks[int(i)].id, float(scores[i])) for i in order if scores[i] > 0]

