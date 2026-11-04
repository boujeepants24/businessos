"""Evaluation: does the pipeline find the right passages, and do answers stay grounded?

Dataset: one JSON object per line (see evals/dataset.example.jsonl):
  {"id": "q1", "question": "...", "expected_sources": ["manual.md"], "answerable": true,
   "must_include": ["F28"]}

Retrieval metrics (free, no API calls):
  hit@k   share of answerable questions with at least one expected source in the top k
  MRR     mean of 1 / rank of the first expected source (0 if absent)
Answer metrics (calls Claude, so they cost money; opt in with --answers):
  answerable accuracy   model's answerable flag matches the label (this is how out-of-scope
                        questions are tested: they must come back answerable=false)
  citation precision    cited excerpts that come from an expected source
  must_include          answers containing every required phrase
  invalid citations     ids the model made up (should always be 0)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .answer import Answerer
from .retrieval import Retriever


@dataclass
class EvalCase:
    id: str
    question: str
    expected_sources: list[str] = field(default_factory=list)
    answerable: bool = True
    must_include: list[str] = field(default_factory=list)


def load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            raw = json.loads(line)
            cases.append(EvalCase(**raw))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"{path}:{n}: invalid eval case ({exc})") from exc
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


def run_eval(
    cases: list[EvalCase], retriever: Retriever, k: int = 6, answerer: Answerer | None = None
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    hits_at_k, reciprocal = [], []
    ans_correct, include_ok, cite_prec, invalid = [], [], [], 0
    cost = 0.0

    for case in cases:
        hits = retriever.search(case.question, k=k)
        sources = [h.chunk.source for h in hits]
        row: dict[str, Any] = {"id": case.id, "retrieved": sources}
        if case.answerable and case.expected_sources:
            rank = next((i for i, s in enumerate(sources, start=1) if s in case.expected_sources), None)
            hits_at_k.append(rank is not None)
            reciprocal.append(1.0 / rank if rank else 0.0)
            row["first_expected_rank"] = rank

        if answerer is not None:
            ans = answerer.answer(case.question, hits)
            cost += ans.estimated_cost_usd
            invalid += len(ans.invalid_citations)
            ans_correct.append(ans.answerable == case.answerable)
            if case.answerable and ans.citations and case.expected_sources:
                good = sum(1 for c in ans.citations if c.source in case.expected_sources)
                cite_prec.append(good / len(ans.citations))
            if case.must_include:
                text = ans.answer.lower()
                include_ok.append(all(p.lower() in text for p in case.must_include))
            row.update(answerable=ans.answerable, status=ans.status, answer=ans.answer)
        rows.append(row)

    def mean(xs: list[float] | list[bool]) -> float | None:
        return round(sum(xs) / len(xs), 3) if xs else None

    summary: dict[str, Any] = {
        "cases": len(cases),
        "k": k,
        f"hit@{k}": mean(hits_at_k),
        "mrr": mean(reciprocal),
    }
    if answerer is not None:
        summary.update(
            answerable_accuracy=mean(ans_correct),
            citation_precision=mean(cite_prec),
            must_include_pass=mean(include_ok),
            invalid_citations=invalid,
            estimated_cost_usd=round(cost, 4),
        )
    return {"summary": summary, "cases": rows}
