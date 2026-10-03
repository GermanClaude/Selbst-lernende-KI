"""Dauerhaftes Gedaechtnis / Lernen.

Die KI lernt nicht, indem ein neuronales Netz neu trainiert wird (das waere
weder lokal noch ueber Nacht moeglich). Stattdessen lernt sie wie ein Mensch,
der sich Dinge notiert: Sie speichert dauerhaft

  * Fakten & Vorlieben ueber dich ("mag keinen Kaffee", "Projektordner ist X"),
  * Korrekturen/Feedback ("nenn mich beim Vornamen"),
  * Gespraechs-Episoden (Kurz-Zusammenfassungen vergangener Sitzungen).

Dieses Wissen wird bei jedem Start in den System-Prompt geladen. So wird die KI
mit jeder Nutzung persoenlicher und treffsicherer - echtes, nachvollziehbares
Lernen, das du sogar in der Datenbank nachlesen und korrigieren kannst.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fact:
    id: int
    category: str
    content: str
    importance: int
    created_at: float
    updated_at: float
    source: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL DEFAULT 'allgemein',
    content     TEXT NOT NULL,
    importance  INTEGER NOT NULL DEFAULT 3,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    source      TEXT NOT NULL DEFAULT 'gespraech'
);
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    summary     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_importance ON facts(importance DESC, updated_at DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content, category, content='facts', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category);
    INSERT INTO facts_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;
"""


class Memory:
    """Verwaltet das dauerhafte Wissen der KI in einer lokalen SQLite-Datei."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._has_fts = True
        try:
            self._conn.executescript(_SCHEMA)
        except sqlite3.OperationalError:
            # SQLite ohne FTS5: Schema ohne Volltextsuche anlegen.
            self._has_fts = False
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'allgemein',
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 3,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'gespraech'
                );
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
        self._conn.commit()

    # -- Schreiben ----------------------------------------------------------
    def remember(
        self,
        content: str,
        category: str = "allgemein",
        importance: int = 3,
        source: str = "gespraech",
    ) -> int:
        """Speichert einen Fakt. Dubletten (gleicher Inhalt) werden aktualisiert."""
        content = content.strip()
        if not content:
            raise ValueError("Leerer Inhalt kann nicht gemerkt werden.")
        importance = max(1, min(5, int(importance)))
        now = time.time()
        existing = self._conn.execute(
            "SELECT id FROM facts WHERE content = ?", (content,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE facts SET importance=?, updated_at=?, category=?, source=? WHERE id=?",
                (importance, now, category, source, existing["id"]),
            )
            self._conn.commit()
            return int(existing["id"])
        cur = self._conn.execute(
            "INSERT INTO facts (category, content, importance, created_at, updated_at, source)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (category, content, importance, now, now, source),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def forget(self, fact_id: int) -> bool:
        """Loescht einen Fakt anhand seiner ID."""
        cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def add_episode(self, summary: str) -> int:
        summary = summary.strip()
        if not summary:
            return 0
        cur = self._conn.execute(
            "INSERT INTO episodes (summary, created_at) VALUES (?, ?)",
            (summary, time.time()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # -- Lesen --------------------------------------------------------------
    def _row_to_fact(self, row: sqlite3.Row) -> Fact:
        return Fact(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            importance=row["importance"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=row["source"],
        )

    def top_facts(self, limit: int = 60) -> list[Fact]:
        """Die wichtigsten/aktuellsten Fakten - fuer den System-Prompt."""
        rows = self._conn.execute(
            "SELECT * FROM facts ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[Fact]:
        """Durchsucht das Gedaechtnis nach einem Stichwort."""
        query = query.strip()
        if not query:
            return []
        if self._has_fts:
            try:
                rows = self._conn.execute(
                    "SELECT f.* FROM facts_fts fts JOIN facts f ON f.id = fts.rowid"
                    " WHERE facts_fts MATCH ? ORDER BY f.importance DESC LIMIT ?",
                    (query, limit),
                ).fetchall()
                return [self._row_to_fact(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE content LIKE ? ORDER BY importance DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def recent_episodes(self, limit: int = 5) -> list[str]:
        rows = self._conn.execute(
            "SELECT summary FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [r["summary"] for r in rows]

    def count_facts(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"])

    # -- Fuer den Prompt ----------------------------------------------------
    def context_block(self, max_facts: int = 60, max_episodes: int = 5) -> str:
        """Formatiert das gespeicherte Wissen als Textblock fuer den System-Prompt."""
        facts = self.top_facts(max_facts)
        episodes = self.recent_episodes(max_episodes)
        if not facts and not episodes:
            return "(Noch nichts gelernt - dies ist ein frueher Moment in unserer Beziehung.)"
        parts: list[str] = []
        if facts:
            parts.append("Was ich ueber meinen Menschen und unsere Zusammenarbeit weiss:")
            for f in facts:
                parts.append(f"  - [{f.category}] {f.content}")
        if episodes:
            parts.append("\nWorum es in letzten Gespraechen ging:")
            for e in episodes:
                parts.append(f"  - {e}")
        return "\n".join(parts)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
