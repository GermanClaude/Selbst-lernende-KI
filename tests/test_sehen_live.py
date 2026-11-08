"""Live-Sehen im Jarvis-Modus: Nova meldet sich nur, wenn du nicht sprichst - und dein Satz geht vor."""
from assistant.live import SEEN_HOLD, LiveLoop, Utterance, is_look_away
from tests.test_live import SETTINGS, FakeEar, FakeHost, FakeVoice, step


class SehHost(FakeHost):
    def __init__(self):
        super().__init__()
        self.seen_turns, self.pausen = [], 0

    def start_seen_turn(self, paket):
        self.seen_turns.append(paket)
        return True

    def seen_pause(self):
        self.pausen += 1


def _loop(host=None):
    host, voice_ = host or SehHost(), FakeVoice()
    return LiveLoop(host, voice_, SETTINGS, ear=FakeEar()), host, voice_


def test_wortmeldung_wartet_bis_du_fertig_bist():
    loop, host, _v = _loop()
    loop.hearing = True
    step(loop, "seen", "paket")
    assert host.seen_turns == [] and loop.seen == "paket"
    loop.hearing = False
    loop._tick()
    assert host.seen_turns == ["paket"] and loop.turn_active and loop.proactive


def test_wortmeldung_wartet_auch_auf_eine_offene_rueckfrage_und_einen_wartenden_satz():
    loop, host, _v = _loop()
    loop.ask_text = "Darf ich?"
    step(loop, "seen", "a")
    assert host.seen_turns == []
    loop.ask_text = None
    loop.pending = "dein Satz"
    host.is_busy = True
    loop._tick()
    assert host.seen_turns == []


def test_zu_alte_wortmeldung_verfaellt():
    loop, host, voice_ = _loop()
    loop.speaking, voice_._idle = True, False
    step(loop, "seen", "alt")
    loop.seen_at -= SEEN_HOLD + 1
    loop.speaking = False
    loop._tick()
    assert host.seen_turns == [] and loop.seen is None


def test_dein_satz_ersetzt_die_wortmeldung_statt_sie_zu_ergaenzen():
    loop, host, voice_ = _loop()
    step(loop, "seen", "paket")
    step(loop, "text", "Da ist ein Fehlerfenster. ")
    assert voice_.said
    step(loop, "utterance", Utterance("Wie spaet ist es", b"", 1.0))
    assert host.cancels == [True]                       # ganz zuruecknehmen, kein "abgebrochen"
    assert loop.pending == "Wie spaet ist es"            # nicht mit der Wortmeldung zusammengefasst
    step(loop, "turn_end", True)
    assert host.turns == ["Wie spaet ist es"] and not loop.proactive


def test_stopp_waehrend_der_wortmeldung_nimmt_sie_ganz_zurueck():
    loop, host, _v = _loop()
    step(loop, "seen", "paket")
    step(loop, "utterance", Utterance("Stopp", b"", 0.5))
    assert host.cancels == [True] and loop.pending is None


def test_schau_weg_pausiert_ohne_ki():
    loop, host, voice_ = _loop()
    loop.hearing = True
    step(loop, "seen", "wartet")
    assert loop.seen == "wartet"
    loop.hearing = False
    loop._handle_utterance(Utterance("Schau weg", b"", 0.6), "Schau weg")
    assert host.pausen == 1 and host.turns == [] and loop.seen is None
    assert voice_.said == ["Okay, ich schaue weg."]
    assert is_look_away("Nicht hinschauen bitte") and is_look_away("Sehen aus")
    assert not is_look_away("Schau mal, wie weit ist der Download weg vom Ziel und sag mir was")
    assert not is_look_away("Wie sieht das Wetter aus")


def test_ohne_live_sehen_im_host_passiert_nichts():
    loop, host, _v = _loop(FakeHost())
    step(loop, "seen", "paket")
    assert loop.seen is None and not loop.turn_active and host.turns == []
    step(loop, "utterance", Utterance("Schau weg", b"", 0.6))
    assert host.turns == ["Schau weg"]                 # ohne Live-Sehen ein ganz normaler Satz


def test_pause_oder_aus_verwirft_die_wartende_wortmeldung():
    loop, host, _v = _loop()
    erlaubt = {"ok": True}
    host.seen_ok = lambda: erlaubt["ok"]
    loop.hearing = True
    step(loop, "seen", "paket")
    assert loop.seen == "paket"
    erlaubt["ok"] = False                                # inzwischen Pause gedrueckt
    loop.hearing = False
    loop._tick()
    assert host.seen_turns == [] and loop.seen is None
    step(loop, "seen", "neu")                            # waehrend der Pause kommt gar nichts an
    assert loop.seen is None


def test_schau_weg_wirkt_auch_mitten_in_einer_antwort():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Erzaehl mir was", b"", 1.0))
    step(loop, "text", "Es war einmal. ")
    loop._handle_utterance(Utterance("Schau weg", b"", 0.6), "Schau weg")
    assert host.pausen == 1 and host.cancels == [] and loop.turn_active   # deine Bitte laeuft weiter
    loop2, host2, _v2 = _loop()
    step(loop2, "seen", "paket")
    loop2._handle_utterance(Utterance("Nicht hinschauen", b"", 0.6), "Nicht hinschauen")
    assert host2.pausen == 1 and host2.cancels == [True]                  # Wortmeldung zurueckgenommen
