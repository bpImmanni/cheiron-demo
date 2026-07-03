"""
database.py
-----------
The data layer. ONE job: save briefs and read them back.

Uses SQLAlchemy, which lets the SAME code work with SQLite (local, a simple
file) or Postgres (production) — we just change the connection string.

DESIGN: saving is NON-BLOCKING. If the database is unreachable, the app must
still work — a storage hiccup should never stop a user getting their brief.
So callers wrap save_brief in try/except and ignore failures gracefully.
"""

import os
import json
import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# The connection string decides WHICH database we use.
# Default: a local SQLite file (briefs.db). In production we'll set DATABASE_URL
# to a Postgres string via an environment variable — no code change needed.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./briefs.db")

# The engine is the core connection to the database.
# (connect_args is a SQLite-only quirk for multi-threaded use; harmless else.)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

# A session factory — sessions are how we talk to the DB (add rows, query, etc.).
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base class our table definitions inherit from.
Base = declarative_base()


class Brief(Base):
    """One row = one saved brief. This defines the TABLE STRUCTURE (schema)."""
    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True)
    brief_markdown = Column(Text)
    score_json = Column(Text)                 # the score dict, stored as JSON text
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# Create the table(s) if they don't exist yet. Safe to call every startup.
Base.metadata.create_all(bind=engine)


def save_brief(query: str, brief_markdown: str, score: dict) -> None:
    """Save one brief. Raises on failure — the CALLER decides how to handle it
    (our backend will ignore failures so the app never breaks on a DB hiccup)."""
    db = SessionLocal()
    try:
        row = Brief(
            query=query,
            brief_markdown=brief_markdown,
            score_json=json.dumps(score),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


def get_recent_briefs(limit: int = 10) -> list[dict]:
    """Return the most recent briefs as a list of dicts."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Brief)
            .order_by(Brief.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "query": r.query,
                "brief_markdown": r.brief_markdown,
                "score": json.loads(r.score_json),
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()


# Isolated test: save two briefs, read them back.
if __name__ == "__main__":
    fake_score = {"accuracy_percent": 100, "valid_ids": ["NCT01"], "invalid_ids": [], "points": 1}

    print("Saving two test briefs...")
    save_brief("semaglutide", "# Test brief one [NCT01]", fake_score)
    save_brief("aspirin", "# Test brief two [NCT02]", fake_score)

    print("Reading them back:\n")
    for b in get_recent_briefs():
        print(f"  #{b['id']}  {b['query']}  ({b['created_at']})  accuracy={b['score']['accuracy_percent']}%")
    print("\nDatabase layer works.")