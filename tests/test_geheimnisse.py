"""Geheimnis-Filter: Passwoerter/Schluessel werden vor dem Speichern unkenntlich gemacht."""
from assistant.geheimnisse import ERSATZ, enthaelt_geheimnis, verschleiere


def test_bekannte_schluessel_praefixe():
    for key in ("sk-proj-ABCDEFGHIJ1234567890", "ak_ABCDEFGHIJ1234567890",
                "AIzaABCDEFGHIJKLMNOPQRSTUVWXYZ12345", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"):
            assert verschleiere(f"mein key {key} ende") == f"mein key {ERSATZ} ende"


def test_jwt_wird_entfernt():
    jwt = "eyJhbGciOiJub25lIn0.eyJ1c2VyIjoieCJ9.abcdef123456"
    assert ERSATZ in verschleiere("token " + jwt)


def test_benannte_passwoerter():
    assert verschleiere("Passwort: hunter2xyz") == "Passwort: " + ERSATZ
    assert verschleiere("mein pin = 123456") == "mein pin: " + ERSATZ
    assert ERSATZ in verschleiere("password=SuperGeheim99")


def test_kartennummer():
    assert ERSATZ in verschleiere("Karte 4111 1111 1111 1111 abgelaufen")


def test_hochentropie_token():
    assert ERSATZ in verschleiere("key AbCd1234EfGh5678IjKl90")  # gemischt, lang -> Geheimnis


def test_normaler_text_bleibt():
    satz = "Hallo Tim, wir treffen uns um 18 Uhr am Bahnhof. Bring bitte den Bericht mit."
    assert verschleiere(satz) == satz
    assert enthaelt_geheimnis(satz) is False
    # kurze/normale Woerter werden nicht angefasst
    assert verschleiere("Das Projekt Nova ist super") == "Das Projekt Nova ist super"


def test_enthaelt_geheimnis():
    assert enthaelt_geheimnis("Passwort: geheim123") is True
    assert enthaelt_geheimnis("") is False


def test_webhooks_und_neue_github_tokens_werden_geschwaerzt():
    from assistant.geheimnisse import ERSATZ, ist_geheimer_name, verschleiere
    text = ("hook https://discord.com/api/webhooks/123456789/abcDEF_ghi-JKL und "
            "github" + "_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz")
    sauber = verschleiere(text)
    assert "abcDEF" not in sauber and "github_pat_" not in sauber and sauber.count(ERSATZ) == 2
    assert ist_geheimer_name("NOVA_DISCORD_WEBHOOK") and ist_geheimer_name("NOVA_PREMIUM_REPO_TOKEN")
