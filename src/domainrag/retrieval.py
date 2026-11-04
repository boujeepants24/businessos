"""Hybrid retrieval: keyword (BM25) and vector search, merged with reciprocal rank fusion.

Why both: keyword search is exact (product codes, error codes like "F28", names), vector search
catches paraphrases ("boiler won't heat" vs "no hot water"). RRF combines two ranked lists without
having to put BM25 scores and cosine similarities on the same scale: each list contributes
1 / (60 + rank) for every chunk it returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .embeddings import Embedder
from .store import Store, StoredChunk
from .text import coverage

RRF_K = 60


@dataclass(frozen=True)
class Hit:
    chunk: StoredChunk
    score: float
    keyword_rank: int | None
    vector_rank: int | None
    vector_score: float | None


class Retriever:
    def __init__(
        self,
        store: Store,
        embedder: Embedder,
        candidates: int = 4,
        min_vector_score: float = 0.05,
        min_coverage: float = 0.5,
        strong_vector_score: float = 0.45,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.candidates = candidates  # each list fetches k * candidates before fusing
        # Vector search always returns *something*, even for an unrelated question. Matches below this
        # cosine similarity are dropped so that "nothing relevant" stays empty instead of padding the
        # context with noise that tempts the model to answer anyway.
        self.min_vector_score = min_vector_score
        # Relevance floor. OR-ed keyword search matches any single shared word ("tax *return*" hits
        # "if F28 *returns*"), so a passage is kept only if it contains at least `min_coverage` of the
        # question's meaningful words, or the embedder rates it a strong semantic match (paraphrases).
        self.min_coverage = min_coverage
        self.strong_vector_score = strong_vector_score

    def search(self, query: str, k: int = 6, sources: Sequence[str] | None = None) -> list[Hit]:
        query = query.strip()
        if not query:
            return []
        n = max(k * self.candidates, 20)
        keyword = self.store.keyword_search(query, n, sources)
        vector = [
            (cid, score)
            for cid, score in self.store.vector_search(self.embedder.embed_query(query), n, sources)
            if score >= self.min_vector_score
        ]

        fused: dict[str, float] = {}
        k_rank: dict[str, int] = {}
        v_rank: dict[str, int] = {}
        v_score: dict[str, float] = {}
        for rank, (cid, _) in enumerate(keyword, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            k_rank[cid] = rank
        for rank, (cid, score) in enumerate(vector, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            v_rank[cid], v_score[cid] = rank, score

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        chunks = self.store.get_chunks([cid for cid, _ in ranked])
        hits: list[Hit] = []
        for cid, score in ranked:
            chunk = chunks.get(cid)
            if chunk is None:
                continue
            strong = v_score.get(cid, 0.0) >= self.strong_vector_score
            if not strong and coverage(query, f"{chunk.title} {chunk.heading} {chunk.text}") < self.min_coverage:
                continue
            hits.append(
                Hit(
                    chunk=chunk,
                    score=score,
                    keyword_rank=k_rank.get(cid),
                    vector_rank=v_rank.get(cid),
                    vector_score=v_score.get(cid),
                )
            )
            if len(hits) == k:
                break
        return hits
