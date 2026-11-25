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
import threading
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


def _locked(method):
    """Fuehrt die Methode unter dem Datenbank-Schloss aus (mehrere Threads)."""
    import functools

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Memory:
    """Verwaltet das dauerhafte Wissen der KI in einer lokalen SQLite-Datei."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Die App greift aus mehreren Threads zu (Antwort, Fenster) - eine Verbindung,
        # durch ein Schloss geschuetzt.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._lock = threading.RLock()
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
        # Vergessene Fakten (fuer den Abgleich PC <-> Cloud: sonst kaemen sie von der anderen Seite zurueck)
        self._conn.execute("CREATE TABLE IF NOT EXISTS vergessen (content TEXT PRIMARY KEY, zeit REAL NOT NULL)")
        self._conn.commit()

    # -- Schreiben ----------------------------------------------------------
    @_locked
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

    @_locked
    def forget(self, fact_id: int) -> bool:
        """Loescht einen Fakt anhand seiner ID."""
        row = self._conn.execute("SELECT content FROM facts WHERE id = ?", (fact_id,)).fetchone()
        cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        if row is not None:
            self._conn.execute("INSERT OR REPLACE INTO vergessen (content, zeit) VALUES (?, ?)",
                               (row["content"], time.time()))
        self._conn.commit()
        return cur.rowcount > 0

    # -- Abgleich (assistant/abgleich.py) -----------------------------------
    @_locked
    def exportieren(self, max_episoden: int = 1000) -> dict:
        """Alles Gelernte als einfache Daten (ohne IDs - die sind auf jedem Geraet anders)."""
        fakten = [{"content": r["content"], "category": r["category"], "importance": r["importance"],
                   "created_at": r["created_at"], "updated_at": r["updated_at"], "source": r["source"]}
                  for r in self._conn.execute("SELECT * FROM facts ORDER BY id")]
        episoden = [{"summary": r["summary"], "created_at": r["created_at"]} for r in self._conn.execute(
            "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (max_episoden,))][::-1]
        vergessen = [{"content": r["content"], "zeit": r["zeit"]}
                     for r in self._conn.execute("SELECT * FROM vergessen ORDER BY zeit")]
        return {"fakten": fakten, "episoden": episoden, "vergessen": vergessen}

    @_locked
    def importieren(self, daten: dict) -> dict:
        """Fuehrt Gelerntes von einem anderen Geraet hier ein. Neueres gewinnt; Vergessenes bleibt vergessen.
        Gibt zurueck, wie viel sich geaendert hat."""
        neu = geaendert = geloescht = episoden = 0
        for v in daten.get("vergessen") or []:
            inhalt, zeit = str(v.get("content") or ""), float(v.get("zeit") or 0)
            if not inhalt:
                continue
            alt = self._conn.execute("SELECT zeit FROM vergessen WHERE content = ?", (inhalt,)).fetchone()
            if alt is None or alt["zeit"] < zeit:
                self._conn.execute("INSERT OR REPLACE INTO vergessen (content, zeit) VALUES (?, ?)", (inhalt, zeit))
            geloescht += self._conn.execute("DELETE FROM facts WHERE content = ? AND updated_at <= ?",
                                            (inhalt, zeit)).rowcount
        for f in daten.get("fakten") or []:
            inhalt = str(f.get("content") or "").strip()
            if not inhalt:
                continue
            aktuell = float(f.get("updated_at") or 0)
            weg = self._conn.execute("SELECT zeit FROM vergessen WHERE content = ?", (inhalt,)).fetchone()
            if weg is not None and weg["zeit"] >= aktuell:
                continue
            werte = (str(f.get("category") or "allgemein"), max(1, min(5, int(f.get("importance") or 3))),
                     aktuell, str(f.get("source") or "abgleich"))
            alt = self._conn.execute("SELECT id, updated_at FROM facts WHERE content = ?", (inhalt,)).fetchone()
            if alt is None:
                self._conn.execute(
                    "INSERT INTO facts (category, content, importance, created_at, updated_at, source)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (werte[0], inhalt, werte[1], float(f.get("created_at") or aktuell), werte[2], werte[3]))
                neu += 1
            elif alt["updated_at"] < aktuell:
                self._conn.execute("UPDATE facts SET category=?, importance=?, updated_at=?, source=? WHERE id=?",
                                   (*werte, alt["id"]))
                geaendert += 1
        for e in daten.get("episoden") or []:
            text, zeit = str(e.get("summary") or "").strip(), float(e.get("created_at") or 0)
            if text and self._conn.execute("SELECT 1 FROM episodes WHERE summary = ? AND abs(created_at - ?) < 0.01",
                                           (text, zeit)).fetchone() is None:
                self._conn.execute("INSERT INTO episodes (summary, created_at) VALUES (?, ?)", (text, zeit))
                episoden += 1
        self._conn.commit()
        return {"neu": neu, "geaendert": geaendert, "geloescht": geloescht, "episoden": episoden}

    @_locked
    def fingerabdruck(self) -> tuple:
        """Billiger Stand: aendert sich, sobald etwas gelernt, geaendert oder vergessen wurde."""
        f = self._conn.execute("SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM facts").fetchone()
        e = self._conn.execute("SELECT COUNT(*), COALESCE(MAX(created_at), 0) FROM episodes").fetchone()
        v = self._conn.execute("SELECT COUNT(*), COALESCE(MAX(zeit), 0) FROM vergessen").fetchone()
        return tuple(f) + tuple(e) + tuple(v)

    @_locked
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

    @_locked
    def top_facts(self, limit: int = 60) -> list[Fact]:
        """Die wichtigsten/aktuellsten Fakten - fuer den System-Prompt."""
        rows = self._conn.execute(
            "SELECT * FROM facts ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    @_locked
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

    @_locked
    def recent_episodes(self, limit: int = 5) -> list[str]:
        rows = self._conn.execute(
            "SELECT summary FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [r["summary"] for r in rows]

    @_locked
    def count_facts(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"])

    # -- Fuer den Prompt ----------------------------------------------------
    @_locked
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

    @_locked
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
