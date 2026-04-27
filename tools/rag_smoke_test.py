"""End-to-end smoke test for the pgvector RAG pipeline.

What it does:
  1. Connects to the configured Postgres (DATABASE_URL).
  2. Loads the embedding model on CPU (~120MB on first run).
  3. Inserts a sample known_fp document for store_id=1.
  4. Runs `evaluate_alert` against three test descriptions and prints
     the verdict + score.
  5. Cleans up the sample document so re-runs are idempotent.

Prereqs:
  - alembic upgrade head (so the `vector` extension + embedding column
    are present)
  - Postgres reachable via DATABASE_URL
  - At least one row in `stores` with id=1 (or change the constant
    below)

Run:
  DATABASE_URL=postgresql://... python tools/rag_smoke_test.py

Exit codes:
  0 — all assertions passed
  1 — DB unreachable / threshold mismatch / regression
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("SECRET_KEY", "smoke-test-secret-do-not-use")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPLIFT_DIR = os.path.join(BASE_DIR, "shoplift_detector")
if SHOPLIFT_DIR not in sys.path:
    sys.path.insert(0, SHOPLIFT_DIR)


STORE_ID = 1


async def main() -> int:
    from app.db.session import AsyncSessionLocal
    from app.services import rag_retriever

    sample_text = (
        "Үйлчлүүлэгч бүтээгдэхүүнийг үзэж байгаад буцааж тавьсан. "
        "Хувцас дотор юу ч нуугаагүй."
    )
    test_cases = [
        (
            "Customer picks up a product and puts it back. No concealment.",
            True,  # Should match the known_fp passage above
        ),
        (
            "Person concealing item under jacket and exiting without paying.",
            False,
        ),
        (
            "Random text totally unrelated to retail. Pizza recipe.",
            False,
        ),
    ]

    print("[1/4] Connecting to Postgres + verifying pgvector extension...")
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text

        try:
            row = (
                await db.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
            ).fetchone()
            if not row:
                print(
                    "  ❌ The `vector` extension is not installed in this DB.\n"
                    "     Run: alembic upgrade head"
                )
                return 1
        except Exception as exc:
            print(f"  ❌ Could not query Postgres: {exc}")
            return 1
    print("  ✅ pgvector ready")

    print(f"[2/4] Inserting sample known_fp document for store_id={STORE_ID}...")
    async with AsyncSessionLocal() as db:
        doc = await rag_retriever.upsert_document(
            db,
            store_id=STORE_ID,
            doc_type="known_fp",
            text=sample_text,
            metadata={"source": "smoke_test"},
        )
        await db.commit()
        await db.refresh(doc)
        sample_id = doc.id
    print(f"  ✅ doc id={sample_id}")

    print("[3/4] Running evaluate_alert against test cases (threshold=0.85)...")
    failures = 0
    async with AsyncSessionLocal() as db:
        for desc, expected_suppress in test_cases:
            decision = await rag_retriever.evaluate_alert(
                db,
                store_id=STORE_ID,
                alert_description=desc,
                fp_threshold=0.85,
            )
            verdict = "SUPPRESS" if decision.should_suppress else "PASS    "
            match = "✅" if decision.should_suppress == expected_suppress else "❌"
            print(
                f"  {match} {verdict} score={decision.fp_score:.3f}  "
                f"expected={'suppress' if expected_suppress else 'pass'}  | {desc[:60]}"
            )
            if decision.should_suppress != expected_suppress:
                failures += 1
                print(f"     reason: {decision.reason}")

    print("[4/4] Cleaning up sample document...")
    async with AsyncSessionLocal() as db:
        from app.db.models.rag_corpus import RagCorpusDocument
        from sqlalchemy import select

        row = (
            await db.execute(
                select(RagCorpusDocument).where(RagCorpusDocument.id == sample_id)
            )
        ).scalar_one_or_none()
        if row:
            await rag_retriever.delete_document(db, row)
            await db.commit()
    print("  ✅ deleted")

    if failures:
        print(f"\n❌ {failures}/{len(test_cases)} assertions failed.")
        return 1
    print("\n✅ All smoke assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
