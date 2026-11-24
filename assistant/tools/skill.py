"""Werkzeug: Nova legt sich selbst Skills an / merkt sich Regeln (gespeicherte Anweisungen).

Ein Skill ist eine kurze Regel in Worten, KEIN Code. Nova wendet eingeschaltete Skills ab dem
naechsten Gespraech an. Gut, wenn dein Mensch sagt "merk dir: fasse dich ab jetzt kurz" o.ae.
"""
from __future__ import annotations

from .base import Tool, ToolContext


class SkillTool(Tool):
    name = "skill"
    description = (
        "Legt eine dauerhafte Regel/Verhaltensweise fuer DICH an (einen 'Skill') oder listet/loescht "
        "sie - z.B. 'Antworte extrem knapp, um Tokens zu sparen'. aktion: 'hinzufuegen' (name, anweisung; "
        "nur_dieses_gehirn=true -> gilt nur fuer das gerade aktive Gehirn, sonst fuer alle), 'liste', "
        "'entfernen' (name). Ein Skill ist eine Anweisung in Worten, KEIN Programmcode. Wirkt ab dem "
        "naechsten Gespraech. Nur anlegen, wenn dein Mensch das moechte oder dir eine Vorliebe nennt."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["hinzufuegen", "liste", "entfernen"]},
            "name": {"type": "string"},
            "anweisung": {"type": "string"},
            "nur_dieses_gehirn": {"type": "boolean"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, name: str = "", anweisung: str = "",
            nur_dieses_gehirn: bool = False) -> str:
        from .. import skills as sk

        config = ctx.extra.get("config")
        if config is None:
            return "Skills koennen hier gerade nicht gespeichert werden."
        root = config.project_root
        if aktion == "liste":
            skills = sk.laden(root)
            if not skills:
                return "Noch keine Skills angelegt."
            return "Skills:\n" + "\n".join(
                f"- {s.name} ({'alle' if not s.provider else s.provider}{'' if s.an else ', aus'}): {s.anweisung}"
                for s in skills)
        if aktion == "entfernen":
            return "Skill geloescht." if sk.entfernen(root, name) else "Keinen Skill mit dem Namen gefunden."
        provider = config.active_provider if nur_dieses_gehirn else ""
        ok, msg = sk.hinzufuegen(root, name, anweisung, provider)
        return msg


def register(registry) -> None:
    registry.register(SkillTool())
