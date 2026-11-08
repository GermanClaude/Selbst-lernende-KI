"""Spielmodus-Steuerung: gemeinsam fuer Terminal (cli.py) und App (controller.py).

Start:   Zustimmung (einmal, und nach einem Gehirn-Wechsel) + ausdruecklicher Start durch dich
         (/spiel start, Knopf im Dialog, oder "Ja" nach einem Vorschlag von Nova). Danach wechselst du
         ins Spiel - Nova erkennt es am Fenster (nur Spiele aus [spiel] erlaubte_spiele, nie Online-Spiele)
         und beginnt erst dann.
Ende:    Bericht (Text + 3-5 Bilder), Kosten zaehlen zur Sitzung der App.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..logging_setup import get_logger
from ..tools.base import ToolContext
from .eingabe import Eingabe, Zielfenster
from .journal import Journal
from .profil import Kalibrierung, erlaubte_profile, finde_profil, klingt_online, online_spiel
from .sitzung import SpielSitzung, grenzen_aus
from .windows import NUR_WINDOWS, WachHalter, parse_taste

logger = get_logger()

START_WARTEN = 120.0  # so lange wartet Nova nach dem Start, dass du ins Spiel wechselst

ZUSTIMMUNG = (
    "**Spielmodus – bitte einmal lesen:**\n"
    "- {name} steuert dann Maus und Tastatur selbst – aber NUR, solange das Spielfenster ({spiele}) vorne "
    "ist. Wechselst du zu einem anderen Fenster, drückt {name} nichts mehr und wartet.\n"
    "- Sofort anhalten: **{taste}** (überall), der Stopp-Knopf, oder einfach die Maus bewegen.\n"
    "- {name} schickt dazu Bilder des Spielfensters an {gehirn}.{kosten}\n"
    "- Nur Einzelspieler-Spiele – nie Online- oder Mehrspieler-Spiele (Regeln, Anti-Cheat, Fairness).\n"
    "- Der Bildschirm darf nicht gesperrt werden (sonst kein Bild und keine Eingabe). {name} hält PC und "
    "Bildschirm während der Sitzung wach – danach wie vorher. Energiesparen/Sperre nach Zeit bitte nicht "
    "erzwingen.\n"
    "- Im Spiel am besten „Randloses Vollbild“ (Borderless) einstellen und das Spiel NICHT als "
    "Administrator starten.\n"
    "- Das gilt auch bei Safe Mode – aber nur für das Spielfenster, nur in dieser Sitzung."
)


class SpielSteuerung:
    def __init__(self, config, permissions, memory, provider_fabrik: Callable[[str, Any, ToolContext], Any],
                 on_notiz: Callable[[str], None] | None = None, on_status: Callable[[], None] | None = None,
                 on_bericht: Callable[[SpielSitzung], None] | None = None,
                 on_vorschlag: Callable[[dict], None] | None = None,
                 nutzung_buchen: Callable[[list], None] | None = None,
                 afk_aktiv: Callable[[], bool] | None = None, sieht_bilder: Callable[[], bool] | None = None,
                 vordergrund: Callable[[], dict | None] | None = None, tasten_fabrik: Callable[[], Any] | None = None,
                 aufnahme: Callable[[tuple], bytes] | None = None, wach_fabrik: Callable[[], WachHalter] | None = None,
                 notaus_fabrik: Callable | None = None, fenster_liste: Callable[[], list] | None = None,
                 ocr: Callable[[bytes], str] | None = None, plattform: str | None = None,
                 speichern: Callable[[str, str], None] | None = None, uhr: Callable[[], float] = time.monotonic,
                 schlafe: Callable[[float], None] = time.sleep):
        self.config = config
        self.permissions = permissions
        self.memory = memory
        self.provider_fabrik = provider_fabrik
        self.on_notiz = on_notiz or (lambda _t: None)
        self.on_status = on_status or (lambda: None)
        self.on_bericht = on_bericht or (lambda _s: None)
        self.on_vorschlag = on_vorschlag or (lambda _v: None)
        self.nutzung_buchen = nutzung_buchen or (lambda _u: None)
        self.afk_aktiv = afk_aktiv or (lambda: False)
        self.sieht_bilder = sieht_bilder or (lambda: True)
        self.plattform = plattform or sys.platform
        self.vordergrund = vordergrund
        self.tasten_fabrik = tasten_fabrik
        self.aufnahme = aufnahme
        self.wach_fabrik = wach_fabrik or WachHalter
        self.notaus_fabrik = notaus_fabrik
        self.fenster_liste = fenster_liste
        self.ocr = ocr
        self.speichern = speichern
        self.uhr = uhr
        self.schlafe = schlafe
        self.sitzung: SpielSitzung | None = None
        self.vorschlag: dict | None = None
        self.letzter_bericht = ""
        self.letzte_sitzung: SpielSitzung | None = None
        self._start: dict | None = None      # Nova wartet, dass du ins Spiel wechselst
        self._start_stopp = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self.rueckkehr: str = ""              # Bericht fuer die naechste Nachricht an Nova

    # -- Einstellungen / Zustimmung ---------------------------------------------------
    @property
    def einst(self):
        return self.config.spiel

    def braucht_zustimmung(self) -> bool:
        s = self.einst
        return not str(s.einverstanden_am or "").strip() or str(s.einverstanden_fuer or "") != str(
            self.config.active_provider)

    def zustimmen(self) -> None:
        from ..config import save_setting, toml_string

        heute = time.strftime("%Y-%m-%d %H:%M")
        self.einst.einverstanden_am = heute
        self.einst.einverstanden_fuer = str(self.config.active_provider)
        for key, wert in (("einverstanden_am", heute), ("einverstanden_fuer", self.einst.einverstanden_fuer)):
            try:
                if self.speichern is not None:
                    self.speichern(key, toml_string(wert))
                else:
                    save_setting(self.config.project_root, "spiel", key, toml_string(wert))
            except Exception as exc:  # noqa: BLE001
                logger.info("Spiel-Zustimmung nicht gespeichert: %s", type(exc).__name__)

    def stopp_taste(self) -> str:
        return str(self.einst.stopp_taste or "Strg+Alt+Umschalt+P")

    def warnung(self) -> str:
        gehirn = {"claude": "Claude von Anthropic", "deepseek": "DeepSeek",
                  "ollama": "Ollama auf deinem PC"}.get(self.config.active_provider, self.config.active_provider)
        kosten = (" Mit Ollama kostet es nichts." if self.config.kostenlos else
                  f" Das kostet Geld – höchstens {_eur(self.einst.max_euro)} € pro Sitzung, nachts "
                  f"{_eur(self.einst.nacht_max_euro)} € (einstellbar).")
        spiele = ", ".join(p.name for p in erlaubte_profile(self.einst.erlaubte_spiele)) or "keins freigegeben"
        return ZUSTIMMUNG.format(name=self.config.ki.name, spiele=spiele, taste=self.stopp_taste(), gehirn=gehirn,
                                 kosten=kosten)

    # -- Zustand ----------------------------------------------------------------------
    @property
    def aktiv(self) -> bool:
        return self._start is not None or (self.sitzung is not None and self.sitzung.laeuft)

    def status(self) -> dict:
        with self._lock:
            sitzung, start = self.sitzung, self._start
        if sitzung is not None and sitzung.laeuft:
            daten = sitzung.status()
        elif start is not None:
            daten = {"aktiv": True, "zustand": "sucht", "spiel": "", "ziel": start["ziel"], "modus": start["modus"],
                     "zuege": 0, "aktionen": 0, "minuten": 0, "eur": 0.0, "max_eur": start["grenzen"].max_euro,
                     "max_minuten": int(start["grenzen"].max_minuten), "max_zuege": start["grenzen"].max_zuege,
                     "kostenlos": bool(self.config.kostenlos),
                     "letztes": "Wechsle jetzt ins Spiel – ich beginne, sobald es vorne ist.", "ende": ""}
        else:
            daten = {"aktiv": False, "zustand": "aus"}
        daten["zustimmung_noetig"] = self.braucht_zustimmung()
        daten["stopp_taste"] = self.stopp_taste()
        daten["spiele"] = [p.name for p in erlaubte_profile(self.einst.erlaubte_spiele)]
        daten["vorschlag"] = dict(self.vorschlag) if self.vorschlag else None
        daten["windows"] = self.plattform == "win32"
        daten["grenzen"] = {"normal": {"stunden": self.einst.max_stunden, "euro": self.einst.max_euro,
                                       "schritte": self.einst.max_schritte},
                            "nacht": {"stunden": self.einst.nacht_max_stunden, "euro": self.einst.nacht_max_euro,
                                      "schritte": self.einst.nacht_max_schritte}}
        return daten

    def laufende_spiele(self) -> list[str]:
        """Welche freigegebenen Spiele gerade ein Fenster haben (fuer den Dialog)."""
        liste = self.fenster_liste
        if liste is None:
            from .windows import fenster_liste as liste
        namen: list[str] = []
        try:
            for info in liste() or []:
                profil = finde_profil(info, self.einst.erlaubte_spiele)
                if profil is not None and profil.name not in namen:
                    namen.append(profil.name)
        except Exception:  # noqa: BLE001
            pass
        return namen

    def _status_neu(self) -> None:
        try:
            self.on_status()
        except Exception:  # noqa: BLE001
            pass

    # -- Vorschlag (Werkzeug spiel_starten) ---------------------------------------------
    def vorschlagen(self, ziel: str, modus: str) -> str:
        if self.aktiv:
            return "Der Spielmodus läuft schon."
        if klingt_online(ziel):
            return ("Nicht vorgeschlagen: Online- oder Mehrspieler-Spiele spiele ich nie selbst (Regeln der Spiele, "
                    "Anti-Cheat, Fairness). Sag das deinem Menschen freundlich.")
        self.vorschlag = {"ziel": str(ziel or "")[:2000], "modus": "nacht" if modus == "nacht" else "normal"}
        try:
            self.on_vorschlag(dict(self.vorschlag))
        except Exception:  # noqa: BLE001
            pass
        self._status_neu()
        return ("Vorgeschlagen: Dein Mensch sieht jetzt den Spielmodus-Dialog (bzw. eine Frage im Terminal) und "
                "startet ihn selbst. Sag ihm kurz, was du vorhast, dass er danach ins Spiel wechseln soll und dass "
                f"{self.stopp_taste()} oder eine Mausbewegung dich sofort anhaelt.")

    # -- Start / Stopp ----------------------------------------------------------------
    def pruefen(self, ziel: str) -> str:
        """'' = darf starten, sonst ein Grund (fuer den Menschen)."""
        if self.plattform != "win32" and self.tasten_fabrik is None:
            return NUR_WINDOWS
        if self.aktiv:
            return "Der Spielmodus läuft schon."
        if self.afk_aktiv() or self.permissions.away:
            return "Während des AFK-Modus gibt es keinen Spielmodus – erst zurückkommen."
        if not self.config.api_key:
            return "Dafür brauche ich erst einen Schlüssel (Gehirn & Schlüssel)."
        if klingt_online(ziel):
            return ("Online- und Mehrspieler-Spiele spiele ich nicht selbst – das verstößt meist gegen "
                    "die Regeln der Spiele (Anti-Cheat) und wäre unfair gegenüber anderen Menschen.")
        if not erlaubte_profile(self.einst.erlaubte_spiele):
            return "In [spiel] erlaubte_spiele ist kein Spiel freigegeben, das ich kenne (z.B. \"manor_lords\")."
        return ""

    def starten(self, ziel: str = "", modus: str = "normal", stunden=None, euro=None, schritte=None,
                einverstanden: bool = False) -> dict:
        ziel = str(ziel or "").strip()[:2000]
        modus = "nacht" if modus == "nacht" else "normal"
        grund = self.pruefen(ziel)
        if grund:
            return {"ok": False, "error": grund}
        if self.braucht_zustimmung():
            if not einverstanden:
                return {"ok": False, "zustimmung": True, "warnung": self.warnung(),
                        "error": "Bitte erst dem Spielmodus zustimmen."}
            self.zustimmen()
        grenzen = grenzen_aus(self.einst, modus, stunden, euro, schritte)
        hinweise = []
        try:
            sieht = bool(self.sieht_bilder())
        except Exception:  # noqa: BLE001
            sieht = False
        if not sieht:
            hinweise.append("Achtung: Dein Modell sieht keine Bilder – der Spielmodus braucht eigentlich ein "
                            "Modell mit Augen (z.B. Claude Sonnet/Haiku, DeepSeek Flash oder ein Ollama-Modell mit "
                            "„vision“). Ich bekomme nur erkannten Text.")
        with self._lock:
            if self.aktiv:
                return {"ok": False, "error": "Der Spielmodus läuft schon."}
            self.vorschlag = None
            self._start_stopp.clear()
            self._start = {"ziel": ziel, "modus": modus, "grenzen": grenzen, "sieht": sieht}
            self._thread = threading.Thread(target=self._lauf, args=(dict(self._start),), name="nova-spiel-start",
                                            daemon=True)
            self._thread.start()
        dauer = (f"{grenzen.max_minuten / 60:.1f}".replace(".", ",").replace(",0", "") + " Std.")
        kosten = "kostenlos" if self.config.kostenlos else f"höchstens ca. {_eur(grenzen.max_euro)} €"
        text = (f"Spielmodus {'(Nacht) ' if modus == 'nacht' else ''}bereit – wechsle jetzt ins Spiel "
                f"(z.B. mit Alt+Tab). Ich beginne, sobald es vorne ist. Grenzen: {dauer}, {kosten}. "
                f"Anhalten: {self.stopp_taste()}, Stopp-Knopf oder Maus bewegen.")
        if hinweise:
            text += "\n" + "\n".join(hinweise)
        self._status_neu()
        return {"ok": True, "text": text, "spiel": self.status()}

    def stoppen(self, grund: str = "nutzer") -> str:
        with self._lock:
            sitzung, start = self.sitzung, self._start
            self.vorschlag = None
        if start is not None:
            self._start_stopp.set()
        if sitzung is not None and sitzung.laeuft:
            sitzung.stop(grund)
            return "Ich halte an – der Bericht kommt gleich."
        if start is not None:
            return "Spielmodus abgebrochen."
        self._status_neu()
        return "Der Spielmodus läuft gerade nicht."

    def warten(self, timeout: float | None = None) -> bool:
        """Bis die Sitzung zu Ende ist (Terminal). True = beendet."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def kalibrieren(self) -> str:
        geloescht = 0
        for profil in erlaubte_profile(self.einst.erlaubte_spiele):
            if self._kalibrierung(profil.id).vergessen():
                geloescht += 1
        sitzung = self.sitzung
        if sitzung is not None and sitzung.laeuft:
            sitzung.kalibrieren_noetig = True
            return "Ich kalibriere im nächsten Zug neu (Positionen der Anzeigen suchen)."
        if geloescht:
            return "Gespeicherte Positionen vergessen – beim nächsten Spielstart kalibriere ich neu."
        return "Es gab noch keine Kalibrierung – die mache ich beim ersten Spielstart automatisch."

    # -- intern -----------------------------------------------------------------------
    def _ordner(self) -> Path:
        return Path(self.config.project_root) / "data" / "spiele"

    def _kalibrierung(self, profil_id: str) -> Kalibrierung:
        return Kalibrierung(self._ordner(), profil_id)

    def _vordergrund(self) -> dict | None:
        if self.vordergrund is not None:
            return self.vordergrund()
        from .windows import vordergrund_info

        return vordergrund_info()

    def _melden(self, text: str) -> None:
        try:
            self.on_notiz(text)
        except Exception:  # noqa: BLE001
            pass

    def _lauf(self, start: dict) -> None:
        try:
            info = self._auf_spiel_warten()
            if info is None:
                return
            sitzung = self._sitzung_bauen(start, info)
            if sitzung is None:
                return
            with self._lock:
                self.sitzung = sitzung
                self._start = None
            self.permissions.begin_spiel(sitzung.profil.name)
            self._melden(f"Ich spiele jetzt {sitzung.profil.name}. Anhalten: {self.stopp_taste()}, Stopp-Knopf "
                         "oder die Maus bewegen.")
            self._status_neu()
            try:
                sitzung.lauf()
            finally:
                self.permissions.end_spiel()
                try:
                    self.nutzung_buchen(sitzung.usages())
                except Exception:  # noqa: BLE001
                    logger.exception("Spielkosten buchen")
                with self._lock:
                    self.letzte_sitzung = sitzung
                    self.letzter_bericht = sitzung.bericht_text
                    self.rueckkehr = sitzung.bericht_text
                try:
                    self.on_bericht(sitzung)
                except Exception:  # noqa: BLE001
                    logger.exception("Spielbericht anzeigen")
        except Exception:  # noqa: BLE001
            logger.exception("Spielmodus")
            self._melden("Der Spielmodus ging nicht (interner Fehler) – ich habe nichts mehr gedrückt.")
        finally:
            with self._lock:
                self._start = None
            self._status_neu()

    def _auf_spiel_warten(self) -> dict | None:
        """Bis ein freigegebenes Spiel vorne ist (hoechstens START_WARTEN Sekunden)."""
        ende = self.uhr() + START_WARTEN
        while self.uhr() < ende:
            if self._start_stopp.is_set():
                self._melden("Spielmodus abgebrochen.")
                return None
            try:
                info = self._vordergrund()
            except Exception:  # noqa: BLE001
                info = None
            online = online_spiel(info)
            if online:
                self._melden(f"{online} ist ein Online-Spiel – das spiele ich nicht selbst. Spielmodus beendet.")
                return None
            if finde_profil(info, self.einst.erlaubte_spiele) is not None:
                return info
            self.schlafe(0.25)
        self._melden("Ich habe kein freigegebenes Spiel im Vordergrund gesehen – Spielmodus beendet. "
                     "Starte das Spiel und versuch es nochmal.")
        return None

    def _sitzung_bauen(self, start: dict, info: dict) -> SpielSitzung | None:
        from ..tools.spiel import spiel_registry

        profil = finde_profil(info, self.einst.erlaubte_spiele)
        if profil is None:
            return None
        if self.tasten_fabrik is not None:
            tasten = self.tasten_fabrik()
        else:
            from .windows import SendInputTasten, dpi_bewusst

            dpi_bewusst()
            try:
                tasten = SendInputTasten()
            except OSError as exc:
                self._melden(str(exc))
                return None
        ziel = Zielfenster(hwnd=int(info.get("hwnd") or 0), pid=int(info.get("pid") or 0),
                           exe=str(info.get("exe") or ""), titel=str(info.get("titel") or ""))
        stopp = threading.Event()
        if self._start_stopp.is_set():
            return None
        eingabe = Eingabe(ziel, profil.erlaubnis(), tasten, self._vordergrund, schlafe=self.schlafe, stopp=stopp,
                          mausbewegung_stoppen=bool(self.einst.bei_mausbewegung_stoppen), uhr=self.uhr)
        ctx = ToolContext(permissions=self.permissions, memory=self.memory, extra={"config": self.config})
        journal = Journal(self._ordner(), profil.id, start["ziel"], start["modus"])
        bilder_ordner = None
        if self.einst.screenshots_speichern:
            bilder_ordner = Path(self.config.workspace_path) / "spiele" / time.strftime("%Y-%m-%d")
        aufnahme = self.aufnahme
        if aufnahme is None:
            from .bild import aufnehmen as aufnahme
        sitzung = SpielSitzung(
            ziel=start["ziel"], modus=start["modus"], profil=profil, grenzen=start["grenzen"], eingabe=eingabe,
            aufnahme=aufnahme, provider_fabrik=self.provider_fabrik, tool_ctx=ctx, registry=spiel_registry(),
            journal=journal, kalibrierung=self._kalibrierung(profil.id), sieht_bilder=start["sieht"],
            kostenlos=bool(self.config.kostenlos), name=self.config.ki.name, raster=bool(self.einst.raster),
            max_kante=int(self.einst.max_kante or 1280), bilder_ordner=bilder_ordner,
            quickload_erlaubt=bool(self.einst.quickload_erlaubt), wach=self.wach_fabrik(),
            notaus=self._notaus_starter(), ocr=self.ocr, uhr=self.uhr, schlafe=self.schlafe,
            on_update=self._status_neu, on_notiz=self._melden)
        if self._start_stopp.is_set():
            sitzung.stop("nutzer")
        return sitzung

    def _notaus_starter(self):
        if self.notaus_fabrik is not None:
            return self.notaus_fabrik
        taste = parse_taste(self.stopp_taste())
        if taste is None or self.plattform != "win32":
            return None

        def starter(gedrueckt):  # pragma: no cover - nur unter Windows
            from .windows import NotAusTaste

            thread = NotAusTaste(taste, gedrueckt)
            thread.start()
            thread.bereit.wait(2.0)
            if thread.ok is False:
                self._melden(f"Hinweis: Die Not-Aus-Taste {self.stopp_taste()} ist schon belegt – anhalten "
                             "geht trotzdem mit dem Stopp-Knopf oder einer Mausbewegung.")
            return thread

        return starter


def _eur(wert: float) -> str:
    try:
        return f"{float(wert):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return "?"
