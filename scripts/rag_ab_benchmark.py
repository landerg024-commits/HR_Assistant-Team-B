#!/usr/bin/env python3
"""Terminal-only, read-only evaluation of live authorized RAG retrieval.

Use external QA references solely for evaluation. This script NEVER injects
expected answers into production Chat Assistant and NEVER rewrites company data.
Each embedding variant gets a DISTINCT temporary Qdrant directory/collection;
there is no mutation of the production vector index.

Output: a TXT diagnostic of candidate-file Recall@k (known target file, where
reference supplies one) and passage lexical-support proxy (NOT answer grade).
The final QA PASS/PARTIAL/FAIL requires a real Chat Assistant run and review.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    p = argparse.ArgumentParser(description="Authorized local RAG candidate diagnostic / embedding A/B")
    p.add_argument("--reference", type=Path, required=True,
                   help="External QA CSV such as Terminal_QA_Test/references/policy_45.csv")
    p.add_argument("--company", default="")
    p.add_argument("--username", default="")
    p.add_argument("--portal", choices=("admin", "employee"), default="admin")
    p.add_argument("--models", nargs="+", default=[],
                   help="Optional second/local model(s); each uses a separate temp Qdrant database")
    p.add_argument("--limit", type=int, default=45)
    p.add_argument("--reranker", choices=("off", "on", "compare"), default="compare",
                   help="Compare the SAME authorized source snapshot with reranker disabled/enabled")
    p.add_argument("--source-map", type=Path, default=None,
                   help="Optional external CSV with id,suggested_source overrides; evaluation-only")
    p.add_argument("--passage-map", type=Path, default=None,
                   help="Optional external CSV with id,evidence_quote columns: exact supporting quotation for passage recall")
    p.add_argument("--report", type=Path, default=ROOT / "logs" / "rag_ab_benchmark.txt")
    return p.parse_args()


def normalized_file(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", Path(str(value or "")).stem.casefold())


def main() -> int:
    a = parse_args()
    if not a.reference.is_file():
        raise SystemExit(f"Missing reference CSV: {a.reference}")
    if a.limit < 1:
        raise SystemExit("--limit must be positive")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from authentication.auth_service import AuthService
    from authentication.access_control import AccessControl
    from database.session import SessionFactory
    from config.chat_assistant_settings import get_chat_assistant_settings
    from modules.smart_ai.portal_ai import PortalKnowledgeBuilder, HybridRetriever, _file_key
    company = a.company or input("Company code: ").strip()
    username = a.username or input("Username: ").strip()
    password = getpass.getpass("Password (hidden): ")
    try:
        with SessionFactory() as session:
            user = AuthService(session).authenticate(company, username, password)
            if user.must_change_password:
                raise PermissionError("Complete password change in normal app first.")
            if a.portal == "admin":
                AccessControl.require_admin(user)
            elif not AccessControl.can_access_employee_portal(user):
                raise PermissionError("Not authorized for Employee portal")
            documents = PortalKnowledgeBuilder(session).build(
                current_user=user, role_scope=a.portal
            )
    finally:
        del password
    rows = list(csv.DictReader(a.reference.open(encoding="utf-8-sig", newline="")))
    rows = [x for x in rows if x.get("question", "").strip()][:a.limit]
    if a.source_map:
        with a.source_map.open(encoding="utf-8-sig", newline="") as fp:
            corrections = {r["id"].strip(): r["suggested_source"].strip()
                           for r in csv.DictReader(fp) if r.get("id") and r.get("suggested_source")}
        for row in rows:
            if row.get("id") in corrections:
                row["suggested_source"] = corrections[row["id"]]
    if a.passage_map:
        with a.passage_map.open(encoding="utf-8-sig", newline="") as fp:
            passages = {r["id"].strip(): r["evidence_quote"].strip()
                        for r in csv.DictReader(fp) if r.get("id") and r.get("evidence_quote")}
        for row in rows:
            if row.get("id") in passages:
                row["evidence_quote"] = passages[row["id"]]
    if not rows:
        raise SystemExit("No valid question rows in reference CSV")
    defaults = get_chat_assistant_settings()
    # Don't download new models just to benchmark: check model cache first.
    from modules.smart_ai.portal_ai import QdrantRetriever, _passage_diagnostic, _LocalCrossEncoder
    models = [defaults.embedding_model] + [m for m in a.models if m != defaults.embedding_model]
    a.report.parent.mkdir(parents=True, exist_ok=True)
    with a.report.open("w", encoding="utf-8") as log, tempfile.TemporaryDirectory(prefix="aihr_rag_ab_") as scratch:
        log.write(f"RAG RETRIEVAL A/B | {datetime.now().isoformat(timespec='seconds')}\n")
        log.write("Company- and account-scoped; no production Qdrant modifications.\n")
        log.write("File recall is a targeted-source diagnostic, NOT answer accuracy.\n\n")
        for model_index, model_name in enumerate(models):
            if model_index and not (Path(model_name).is_dir() or QdrantRetriever._cached_embedding_source(model_name)):
                log.write(f"SKIPPED model={model_name}: not in local cache. No downloads.\n")
                continue
            modes = ("off", "on") if a.reranker == "compare" else (a.reranker,)
            try:
                model_source = (_LocalCrossEncoder.get(defaults.reranker_model, local_only=True)
                                if "on" in modes else None)
            except (ImportError, RuntimeError, OSError, ValueError) as exc:
                model_source = None
                log.write(f"SKIPPED reranker model={defaults.reranker_model}: {type(exc).__name__}.\n")
            for mode in modes:
                if mode == "on" and model_source is None:
                    log.write(f"SKIPPED reranker=on model={defaults.reranker_model}: not locally cached.\n")
                    continue
                os.environ["SMART_AI_EMBEDDING_MODEL"] = model_name
                os.environ["SMART_AI_QDRANT_DIR"] = str(Path(scratch) / f"candidate_{model_index}")
                os.environ["SMART_AI_QDRANT_COLLECTION"] = f"hr_ab_{model_index}"
                os.environ["SMART_AI_RERANKER_ENABLED"] = "true" if mode == "on" else "false"
                get_chat_assistant_settings.cache_clear()
                retriever = HybridRetriever()
                hits, tested, candidate_seconds = 0, 0, 0.0
                passage_hits, passage_tested = 0, 0
                body_coverage = []
                log.write(f"\nMODEL {model_name} | RERANKER {mode}\n")
                for idx, row in enumerate(rows, 1):
                    question = str(row.get("question") or "").strip()
                    wanted = normalized_file(str(row.get("suggested_source") or ""))
                    started = time.perf_counter()
                    results = retriever.search(
                        question, documents, company_id=user.company_id,
                        role_scope=a.portal,
                        access_partition=f"company:{user.company_id}:role:{a.portal}:user:{user.user_id}:AB:{model_index}",
                    )
                    elapsed = time.perf_counter()-started
                    candidate_seconds += elapsed
                    sources = [normalized_file(str(item.document.metadata.get("filename") or item.document.title))
                               for item in results if _file_key(item.document)]
                    match = bool(wanted and wanted in sources)
                    if wanted:
                        tested += 1
                        hits += int(match)
                    passages = [ _passage_diagnostic(question, item.document) for item in results
                                 if _file_key(item.document) ]
                    quoted = " ".join(str(row.get("evidence_quote") or "").casefold().split())
                    exact_passage = None
                    if quoted:
                        passage_tested += 1
                        exact_passage = any(quoted in " ".join(item.document.text.casefold().split())
                                            for item in results)
                        passage_hits += int(exact_passage)
                    # A lexical coverage proxy is not an answer/citation grade.
                    best_passage = max((float(x["body_coverage"]) for x in passages), default=0.0)
                    body_coverage.append(best_passage)
                    log.write(f"{idx:03d} | {row.get('id','-')} | top6_file_match={match if wanted else 'UNSPECIFIED'} "
                              f"| exact_passage_hit={exact_passage if exact_passage is not None else 'UNSPECIFIED'} "
                              f"| best_passage_body_coverage={best_passage:.3f} "
                              f"| sections={';'.join(str(x['section'])[:60] for x in passages[:3]) or '(none)'} "
                              f"| seconds={elapsed:.3f} | candidates={','.join(sources[:6]) or '(none)'}\n")
                    print(f"[model {model_index+1}/{len(models)} | rerank {mode}] {idx}/{len(rows)} {elapsed:.2f}s", flush=True)
                log.write(f"SUMMARY: expected-source top6={hits}/{tested} (only labeled cases); "
                          f"exact-passage recall={passage_hits}/{passage_tested} (only provided verbatim quotes); "
                          f"mean_best_passage_body_coverage={sum(body_coverage)/max(1,len(body_coverage)):.3f}; "
                          f"candidate_total_s={candidate_seconds:.2f}; "
                          f"vector_diagnostic={retriever.vector.diagnostic}\n")
        # The A/B run owns only temporary clients. Close them *before* Python
        # shutdown to avoid QdrantClient.__del__ interpreter-exit warnings.
        # Do not close any production client or change its collection.
        from modules.smart_ai.portal_ai import QdrantRetriever as _Vector
        with _Vector._client_lock:
            owned = [key for key in list(_Vector._clients) if "aihr_rag_ab_" in key]
            for key in owned:
                client = _Vector._clients.pop(key, None)
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
    get_chat_assistant_settings.cache_clear()
    print(f"Saved read-only A/B report: {a.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
