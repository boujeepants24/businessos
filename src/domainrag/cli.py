"""Command line: domainrag {ingest,search,ask,eval,status,serve}."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .answer import Answerer, AnswerError
from .chunking import section_label
from .config import Settings
from .embeddings import make_embedder
from .evals import load_dataset, run_eval
from .ingest import ingest
from .retrieval import Retriever
from .store import EmbedderMismatch, Store


def _setup(settings: Settings) -> tuple[Store, Retriever]:
    settings.validate()
    store = Store(settings.db_path)
    embedder = make_embedder(settings)
    if store.get_meta("embedder"):
        store.bind_embedder(embedder.name)
    return store, Retriever(store, embedder)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="domainrag", description="Retrieval-augmented answers over one knowledge folder."
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="index the knowledge folder (only changed files)")
    p_ing.add_argument("--rebuild", action="store_true", help="drop the index and re-embed everything")

    p_search = sub.add_parser("search", help="show the passages retrieved for a query")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=5)

    p_ask = sub.add_parser("ask", help="answer a question with citations (calls Claude)")
    p_ask.add_argument("question")
    p_ask.add_argument("--json", action="store_true")

    p_eval = sub.add_parser("eval", help="measure retrieval (and optionally answers) on a dataset")
    p_eval.add_argument("dataset", type=Path)
    p_eval.add_argument("-k", type=int, default=6)
    p_eval.add_argument("--answers", action="store_true", help="also grade Claude's answers (costs money)")
    p_eval.add_argument("--out", type=Path, help="write the full per-case report as JSON")

    sub.add_parser("status", help="index size and settings")
    sub.add_parser("serve", help="run the MCP server on stdio")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()

    try:
        if args.command == "ingest":
            settings.validate()
            store = Store(settings.db_path)
            if not settings.docs_dir.exists():
                print(
                    f"Knowledge folder {settings.docs_dir} does not exist. Create it and add documents.",
                    file=sys.stderr,
                )
                return 1
            report = ingest(settings, store, make_embedder(settings), rebuild=args.rebuild)
            print(report.summary())
            for source, err in report.failed.items():
                print(f"  failed: {source}: {err}", file=sys.stderr)
            return 1 if report.failed else 0

        store, retriever = _setup(settings)

        if args.command == "status":
            print(store.export_json())
        elif args.command == "search":
            for n, h in enumerate(retriever.search(args.query, k=args.k), start=1):
                where = section_label(h.chunk.title, h.chunk.heading)
                print(f"{n}. [{h.chunk.id}] {h.chunk.source} | {where} | score {h.score:.4f}")
                print("   " + h.chunk.text[:300].replace("\n", " ") + ("…" if len(h.chunk.text) > 300 else ""))
        elif args.command == "ask":
            answerer = Answerer(settings.domain, settings.claude_model, settings.effort)
            result = answerer.answer(args.question, retriever.search(args.question, k=settings.top_k))
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(result.answer)
                for c in result.citations:
                    print(f"  [{c.excerpt_id}] {c.source} | {c.section}")
                print(
                    f"\n({result.status}; {result.input_tokens} in / {result.output_tokens} out tokens; {result.latency_ms} ms; ~${result.estimated_cost_usd})",
                    file=sys.stderr,
                )
        elif args.command == "eval":
            cases = load_dataset(args.dataset)
            if not cases:
                print("The dataset has no cases yet. Add questions once the knowledge folder has documents.")
                return 0
            eval_answerer = Answerer(settings.domain, settings.claude_model, settings.effort) if args.answers else None
            eval_report = run_eval(cases, retriever, k=args.k, answerer=eval_answerer)
            print(json.dumps(eval_report["summary"], indent=2))
            if args.out:
                args.out.write_text(json.dumps(eval_report, indent=2), encoding="utf-8")
        elif args.command == "serve":
            from .mcp_server import build_server

            answerer = Answerer(settings.domain, settings.claude_model, settings.effort)
            build_server(settings, store, retriever.embedder, answerer).run("stdio")
        return 0
    except (EmbedderMismatch, AnswerError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
