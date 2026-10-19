"""Read-only preflight for the local policy knowledge corpus.

This script does not read QA answer keys, call an LLM, create embeddings,
modify SQLite records, or disclose policy contents. It reports whether the
published, effective policies needed for RAG are present in the database.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sqlite3
import sys


def summarize(db: Path, company_id: int, *, on_date: str | None = None) -> dict:
    if not db.is_file():
        raise FileNotFoundError(f"SQLite database not found: {db}")
    as_of = on_date or date.today().isoformat()
    # URI mode=ro + query_only avoids accidental mutation or migrations.
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        counts = con.execute("""
            SELECT
                (SELECT count(*) FROM hr_policies WHERE company_id=?),
                (SELECT count(*) FROM hr_policies WHERE company_id=? AND status='published'
                    AND (effective_date IS NULL OR effective_date<=?)),
                (SELECT count(*) FROM hr_policies WHERE company_id=? AND status='trashed')
        """, (company_id, company_id, as_of, company_id)).fetchone()
        rows = con.execute("""
            SELECT p.id, p.title,
                   COALESCE(length(trim(p.content)), 0) as content_chars,
                   COUNT(DISTINCT s.id) as section_count
            FROM hr_policies AS p
            LEFT JOIN hr_policy_documents AS d
              ON d.policy_id=p.id AND d.company_id=p.company_id
            LEFT JOIN hr_policy_sections AS s
              ON s.document_id=d.id AND s.policy_id=p.id AND s.company_id=p.company_id
            WHERE p.company_id=? AND p.status='published'
                AND (p.effective_date IS NULL OR p.effective_date<=?)
            GROUP BY p.id,p.title,p.content
            ORDER BY p.title
        """, (company_id, as_of)).fetchall()
        return {"company_id": company_id, "date": as_of,
                "policies_total": counts[0], "published_effective": counts[1],
                "trashed": counts[2],
                "published_text_only": sum(bool(chars) and sections == 0 for _,_,chars,sections in rows),
                "published_file_backed": sum(sections > 0 for _,_,chars,sections in rows),
                "published_empty": sum(not chars and not sections for _,_,chars,sections in rows),
                "source_titles": [title for _,title,chars,sections in rows if chars or sections]}
    finally:
        con.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/hr_assistant.db"))
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--date", help="As-of ISO date, default local day (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    try:
        result = summarize(args.db, args.company_id, on_date=args.date)
    except (sqlite3.Error, FileNotFoundError, ValueError) as exc:
        print(f"READ-ONLY POLICY PREFLIGHT ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Company ID: {result['company_id']} | As of: {result['date']}")
    for key in ("policies_total", "published_effective", "trashed", "published_text_only",
                "published_file_backed", "published_empty"):
        print(f"{key}: {result[key]}")
    print("Available published/effective policy titles:")
    for title in result["source_titles"]:
        print(f"  - {title}")
    if not result["source_titles"]:
        print("  (none; policy questions cannot be answered from an empty policy corpus)")
    print("Read-only preflight finished; no database records changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
