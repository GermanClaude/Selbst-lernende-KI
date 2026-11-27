"""Werkzeug 'zugang': Nova verwaltet deine Logins ueber den verschluesselten Zugangs-Tresor (assistant/tresor.py).

Wichtig fuer die Sicherheit: Dieses Werkzeug gibt NIE ein Passwort als Text aus und nimmt auch keines im Chat
entgegen (sonst liefe es durch den KI-Anbieter). Passwoerter traegt dein Mensch selbst im Tresor ein
(Befehl /zugang bzw. die App). Beim 'einloggen' tippt die App das Passwort direkt ins Loginfeld - es kommt nie
zurueck zur KI.
"""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext


class ZugangTool(Tool):
    name = "zugang"
    description = (
        "Verwaltet die gespeicherten Logins deines Menschen (verschluesselter Tresor, nur auf diesem Geraet). "
        "aktion: 'status' (ist der Tresor da/offen?), 'liste' (Dienste + Benutzernamen - NIE Passwoerter), "
        "'merken' (dienst, benutzer, url, notiz anlegen/aendern - ein PASSWORT kannst du hier NICHT setzen, das "
        "macht dein Mensch mit /zugang bzw. in der App), 'entfernen' (dienst), 'einloggen' (dienst - meldet "
        "dich beim Dienst an, indem die App Benutzer und Passwort direkt ins Loginfeld tippt; du erfaehrst das "
        "Passwort dabei nicht). Nutze 'einloggen' erst, wenn die Login-Seite offen und das Feld sichtbar ist. "
        "Du gibst Passwoerter niemals heraus und fragst auch nie danach - der Tresor ist dafuer da."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["status", "liste", "merken", "entfernen", "einloggen"]},
            "dienst": {"type": "string"},
            "benutzer": {"type": "string"},
            "url": {"type": "string"},
            "notiz": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, dienst: str = "", benutzer: str = "", url: str = "",
            notiz: str = "") -> str:
        from .. import tresor as T

        root = ctx.extra.get("app_root") or getattr(ctx.permissions, "app_root", None)
        if root is None:
            return "Der Tresor ist hier gerade nicht verfuegbar."
        try:
            if aktion == "status":
                return T.status_text(root)
            if aktion == "liste":
                eintraege = T.liste(root)
                if not eintraege:
                    return "Im Tresor ist noch nichts. Dein Mensch kann mit /zugang Logins eintragen."
                return "Gespeicherte Logins:\n" + "\n".join(
                    f"- {e['dienst']}" + (f" (Benutzer: {e['benutzer']})" if e['benutzer'] else "")
                    + ("" if e['hat_passwort'] else " [kein Passwort hinterlegt]") for e in eintraege)
            if aktion == "merken":
                # Nur nicht-geheime Felder - das Passwort setzt der Mensch ueber /zugang.
                if not dienst:
                    return "Fuer welchen Dienst? (dienst fehlt)"
                ctx.permissions.require(Risk.MODERATE, f"Login-Eintrag '{dienst}' anlegen/aendern (ohne Passwort)")
                T.eintrag(root, dienst, benutzer=benutzer, url=url, notiz=notiz)
                return (f"'{dienst}' gespeichert (Benutzer/URL/Notiz). Das PASSWORT trag bitte selbst ein: "
                        f"/zugang passwort {dienst}  - so laeuft es nie durch den Chat.")
            if aktion == "entfernen":
                return f"'{dienst}' entfernt." if T.entfernen(root, dienst) else f"'{dienst}' war nicht im Tresor."
            if aktion == "einloggen":
                if not T.hat(root, dienst):
                    return f"Fuer '{dienst}' ist nichts im Tresor. Erst mit /zugang anlegen."
                filler = ctx.extra.get("tresor_filler")
                if not callable(filler):
                    return ("Automatisches Einloggen geht in dieser Ansicht nicht. Oeffne die Login-Seite; dein "
                            "Mensch kann das Passwort aus dem Tresor einsetzen (/zugang).")
                ctx.permissions.require(Risk.DANGEROUS,
                                        f"Bei '{dienst}' anmelden (Benutzer und Passwort ins Loginfeld tippen)")
                try:
                    daten = T.geheimnis_fuer_login(root, dienst)   # bleibt in dieser Schicht
                except T.TresorFehler as exc:
                    return str(exc)
                ok = filler(daten)        # tippt Benutzer+Passwort; gibt NIE das Passwort zurueck
                return (f"Benutzer und Passwort fuer '{daten['dienst']}' ins Loginfeld getippt. Pruefe, ob die "
                        "Anmeldung durchgeht." if ok else
                        "Konnte gerade nichts eintippen - ist ein Eingabefeld ausgewaehlt?")
        except T.TresorFehler as exc:
            return str(exc)
        return "Unbekannte Aktion."


def register(registry) -> None:
    registry.register(ZugangTool())
