"""Live-Sprachmodus: Saetze schneiden, durchgehend zuhoeren, unterbrechen, Nachtraege."""
import io
import json
import queue
import threading
import time
import zipfile
from array import array
from types import SimpleNamespace

import pytest

from assistant import live
from assistant.live import Ear, LiveLoop, SentenceSplitter, Utterance, voice_choice


# -- Saetze -----------------------------------------------------------------
def test_first_sentence_comes_immediately_and_rest_is_grouped():
    sp = SentenceSplitter()
    assert sp.feed("Klar") == []
    assert sp.feed("! Das ") == ["Klar!"]                       # erster Satz sofort
    assert sp.feed("geht. Am 3. Mai, z.B. um 9 Uhr. ") == []    # kurze Saetze sammeln, "3." / "z.B." kein Ende
    out = sp.feed("Dann noch ein langer Satz, damit es reicht. ")
    assert out == ["Das geht. Am 3. Mai, z.B. um 9 Uhr. Dann noch ein langer Satz, damit es reicht."]
    assert sp.feed("Ende") == [] and sp.flush() == ["Ende"]


def test_code_blocks_and_markdown_are_not_read_aloud():
    sp = SentenceSplitter(min_len=1)
    out = sp.feed("## Plan\n**Schritt eins:** los.\n```python\nprint('x')\n")
    assert out == ["Plan", "Schritt eins: los."]                 # Code noch offen: warten
    out = sp.feed("```\nFertig.\n")
    assert out == ["Den Code siehst du auf dem Bildschirm.", "Fertig."]
    assert all("`" not in x and "*" not in x for x in out)


def test_tool_lines_are_split_off():
    text, tool = live.split_tool_lines("Ich schaue nach.\n  … nutze Werkzeug: web_suche\n")
    assert tool and "Werkzeug" not in text and "Ich schaue nach." in text
    assert live.split_tool_lines("Hallo") == ("Hallo", False)


def test_voice_answers_to_questions():
    assert voice_choice("Ja, mach.", ["einmal", "immer", "nein"]) == "einmal"
    assert voice_choice("Immer erlauben", ["einmal", "immer", "nein"]) == "immer"
    assert voice_choice("Nein, lieber nicht", ["einmal", "immer", "nein"]) == "nein"
    assert voice_choice("ja", ["ja", "nein"]) == "ja"
    assert voice_choice("Was willst du denn da genau schreiben?", ["einmal", "nein"]) is None
    assert live.is_stop("Stopp!") and live.is_stop("hör auf") and not live.is_stop("Wie wird das Wetter?")


# -- Zuhoeren ----------------------------------------------------------------
def _block(level, ms=50):
    n = 16 * ms
    return array("h", [level, -level] * (n // 2)).tobytes()


class FakeSD:
    def __init__(self, blocks, before_each=None):
        self.blocks = blocks
        self.before_each = before_each

    def RawInputStream(self, callback, **kw):  # noqa: N802
        fake = self

        class Stream:
            def __enter__(self):
                def feed():
                    for i, b in enumerate(fake.blocks):
                        if fake.before_each:
                            fake.before_each(i)
                        callback(b, len(b) // 2, None, None)
                        time.sleep(0.001)
                threading.Thread(target=feed, daemon=True).start()
                return self

            def __exit__(self, *a):
                return False

        return Stream()


def _run_ear(blocks, wait_for, timeout=5, **kw):
    got: queue.Queue = queue.Queue()
    ear = Ear(lambda kind, data: got.put((kind, data)), sd_module=FakeSD(blocks, kw.pop("before_each", None)),
              **kw)
    ear.start()
    seen, end = [], time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            try:
                kind, data = got.get(timeout=0.1)
            except queue.Empty:
                continue
            seen.append((kind, data))
            if kind == wait_for:
                return seen, ear
    finally:
        ear.stop()
    raise AssertionError(f"kein {wait_for}: {[k for k, _ in seen]}")


class FakeRecognizer:
    def __init__(self):
        self.fed = 0

    def reset(self):
        self.fed = 0

    def feed(self, pcm):
        self.fed += len(pcm)
        return "wie wird" if self.fed < 16000 else "wie wird das wetter"

    def finish(self):
        return "wie wird das wetter morgen"


def test_ear_hears_a_sentence_after_a_short_pause_with_live_text():
    quiet, loud = _block(40), _block(4000)
    blocks = [quiet] * 12 + [loud] * 24 + [quiet] * 16 + [loud] * 10
    seen, _ = _run_ear(blocks, "utterance", pause=0.7, recognizer_factory=FakeRecognizer)
    kinds = [k for k, _ in seen]
    assert kinds.index("onset") < kinds.index("partial") < kinds.index("utterance")
    utt = seen[-1][1]
    assert utt.text == "Wie wird das wetter morgen"             # sofort fertig, ohne Google
    assert 1.6 <= utt.seconds <= 2.3                             # Vorlauf + 1,2 s Sprache + 0,7 s Pause
    assert any(k == "level" for k in kinds)


def test_ear_ignores_a_click_and_works_without_live_recognizer():
    quiet, loud = _block(40), _block(4000)
    seen, _ = _run_ear([quiet] * 12 + [loud] * 3 + [quiet] * 16, "dropped")   # 150 ms Knacks
    assert "utterance" not in [k for k, _ in seen]
    seen, _ = _run_ear([quiet] * 12 + [loud] * 10 + [quiet] * 16, "utterance")
    assert seen[-1][1].text is None and seen[-1][1].pcm            # -> Google/Whisper wandelt um


def test_ear_barge_in_needs_more_than_novas_own_echo():
    quiet, echo, voice_ = _block(40), _block(1500), _block(9000)
    ear_box = {}

    def nova_talks(i):
        if i == 12 and "ear" in ear_box:
            ear_box["ear"].set_nova_speaking(True)

    # Nova spricht (Echo 1500) - das allein darf nicht als Dazwischenreden zaehlen
    blocks = [quiet] * 12 + [echo] * 40 + [voice_] * 10 + [quiet] * 20
    got: queue.Queue = queue.Queue()
    ear = Ear(lambda k, d: got.put((k, d)), sd_module=FakeSD(blocks, nova_talks), pause=0.7)
    ear_box["ear"] = ear
    ear.start()
    kinds, end = [], time.monotonic() + 5
    while time.monotonic() < end and "utterance" not in kinds:
        try:
            kinds.append(got.get(timeout=0.1)[0])
        except queue.Empty:
            pass
    ear.stop()
    assert "barge" in kinds and "onset" not in kinds
    assert kinds.index("barge") < kinds.index("utterance")


# -- Gespraech ----------------------------------------------------------------
class FakeHost:
    def __init__(self):
        self.events, self.turns, self.cancels, self.answers = [], [], [], []
        self.ask = None
        self.is_busy = False

    def event(self, e):
        self.events.append(e)

    def busy(self):
        return self.is_busy

    def start_turn(self, text):
        self.turns.append(text)
        return True

    def cancel_turn(self, drop):
        self.cancels.append(drop)

    def transcribe(self, pcm):
        return "aus der genauen erkennung"

    def pending_ask(self):
        return self.ask

    def answer_ask(self, ask_id, value):
        self.answers.append((ask_id, value))

    def is_exit(self, text):
        return "chat-modus" in text.lower()

    def states(self):
        return [e["state"] for e in self.events if e["type"] == "jarvis"]


class FakeVoice:
    def __init__(self):
        self.said, self.ended = [], []
        self.stopped = 0
        self._idle = True

    def begin(self, turn):
        self.turn = turn

    def say(self, text, seq):
        self.said.append(text)
        self._idle = False

    def end(self, count):
        self.ended.append(count)

    def stop(self):
        self.stopped += 1
        self._idle = True

    def spoken(self, turn=None, seq=None):
        self._idle = True

    def idle(self):
        return self._idle


class FakeEar:
    live = False

    def __init__(self):
        self.nova = []

    def start(self):
        pass

    def stop(self):
        pass

    def set_nova_speaking(self, value):
        self.nova.append(value)


SETTINGS = SimpleNamespace(pause=0.7, unterbrechen=True, live_genau=False)


def _loop():
    host, voice_ = FakeHost(), FakeVoice()
    loop = LiveLoop(host, voice_, SETTINGS, ear=FakeEar())
    return loop, host, voice_


def step(loop, kind, data=None):
    getattr(loop, f"_on_{kind}")(data)
    loop._tick()


def test_answer_is_spoken_sentence_by_sentence_while_it_streams():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Wie wird das Wetter morgen", b"", 1.0))
    assert host.turns == ["Wie wird das Wetter morgen"] and host.states()[-1] == "thinking"
    step(loop, "text", "Morgen wird es sonnig")
    assert voice_.said == []
    step(loop, "text", ". Am Nachmittag ")
    assert voice_.said == ["Morgen wird es sonnig."]             # spricht, waehrend der Rest noch kommt
    assert loop.ear.nova == [True] and host.states()[-1] == "speaking"
    step(loop, "text", "bis 24 Grad.")
    step(loop, "turn_end")
    assert voice_.said[-1] == "Am Nachmittag bis 24 Grad." and voice_.ended == [2]
    assert loop.speaking                                          # liest noch vor
    step(loop, "spoken", None)
    assert not loop.speaking and host.states()[-1] == "listening" and loop.ear.nova[-1] is False


def test_talking_over_nova_stops_her_at_once():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Erzaehl mir was", b"", 1.0))
    step(loop, "text", "Es war einmal ein König. Der hatte ")
    assert loop.speaking
    step(loop, "barge")
    assert voice_.stopped == 1 and not loop.speaking and host.cancels == []   # sofort still
    step(loop, "text", "drei Töchter. ")                       # waehrend du sprichst: nicht vorlesen
    assert voice_.said == ["Es war einmal ein König."]
    step(loop, "utterance", Utterance("Nein erzähl lieber einen Witz", b"", 1.0))
    assert host.cancels == [False]                               # jetzt erst anhalten
    assert host.turns == ["Erzaehl mir was"]                     # wartet, bis die alte Antwort weg ist
    step(loop, "turn_end", True)
    assert host.turns[-1] == "Nein erzähl lieber einen Witz"


def test_a_noise_while_nova_speaks_does_not_lose_the_answer():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Erzaehl mir was", b"", 1.0))
    step(loop, "text", "Es war einmal ein König. ")
    step(loop, "barge")
    step(loop, "dropped")                                         # war nur ein Husten
    step(loop, "text", "Der hatte drei Töchter, die alle sehr klug waren und viel lasen. ")
    assert host.cancels == [] and voice_.said[-1].startswith("Der hatte drei Töchter")


def test_afterthought_is_merged_into_the_question():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Wie wird das Wetter morgen", b"", 1.0))
    step(loop, "utterance", Utterance("in Berlin", b"", 0.6))     # Nova hat noch nichts gesagt
    assert host.cancels == [True]                                # alte Runde ganz zuruecknehmen
    step(loop, "turn_end", True)
    assert host.turns == ["Wie wird das Wetter morgen", "Wie wird das Wetter morgen in Berlin"]


def test_while_working_new_wishes_wait_but_stop_works():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Programmier das Spiel um", b"", 1.0))
    step(loop, "text", "Ich lese erst die Dateien.\n")
    step(loop, "tool")
    step(loop, "utterance", Utterance("Und mach die Türen rot", b"", 1.0))
    assert host.cancels == [] and "gleich" in voice_.said[-1]   # nicht mittendrin abbrechen
    step(loop, "text", "Fertig, alles umgebaut.")
    step(loop, "turn_end")
    assert host.turns == ["Programmier das Spiel um"]            # erst ausreden lassen
    step(loop, "spoken")
    assert host.turns[-1] == "Und mach die Türen rot"
    step(loop, "tool")
    step(loop, "utterance", Utterance("Stopp", b"", 0.5))
    assert host.cancels == [False]


def test_questions_can_be_answered_by_voice_and_exit_phrase_ends():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Schreib die Datei", b"", 1.0))
    step(loop, "tool")
    host.ask = {"id": "q1", "options": ["einmal", "immer", "nein"]}
    step(loop, "ask", "Die KI moechte figuren.py schreiben. Risiko: mittel")
    assert voice_.said[-1].startswith("Kurze Rückfrage: Die KI möchte figuren.py schreiben")
    step(loop, "utterance", Utterance("Ja klar", b"", 0.0))
    assert host.answers == [("q1", "einmal")] and host.cancels == []
    host.ask = None
    step(loop, "turn_end")
    step(loop, "spoken")
    step(loop, "utterance", Utterance("Chat-Modus bitte", b"", 0.5))
    assert loop.stop_event.is_set()


def test_without_live_recognizer_the_precise_one_is_used():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance(None, b"\x00\x01" * 100, 1.0))
    assert host.turns == ["Aus der genauen erkennung"] and "recognizing" in host.states()


def test_loop_runs_and_stops_cleanly():
    loop, host, voice_ = _loop()
    thread = threading.Thread(target=loop.run, daemon=True)
    thread.start()
    loop.post("utterance", Utterance("Hallo Nova", b"", 0.5))
    loop.on_text("Hallo! Schön dich zu hören. ")
    time.sleep(0.3)
    loop.stop()
    thread.join(3)
    assert not thread.is_alive()
    assert host.turns == ["Hallo Nova"] and voice_.said == ["Hallo!"]
    assert host.cancels == [False] and host.states()[-1] == "off"   # laufende Antwort angehalten


# -- Modell laden & Verlauf zuruecknehmen --------------------------------------------
def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


class _Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_model_download_unpacks_into_data_and_rejects_bad_archives(tmp_path):
    settings = SimpleNamespace(sprache="de", live_modell="", live_mitschrift=True)
    name = "vosk-model-small-de-0.15"
    data = _zip({f"{name}/am/final.mdl": "x", f"{name}/conf/model.conf": "y"})
    seen = []
    path = live.download_model(tmp_path, settings, progress=lambda d, t: seen.append(d),
                               urlopen=lambda url, timeout: (seen.append(url), _Resp(data))[1])
    assert path == tmp_path / "data" / "sprachmodelle" / name and (path / "am" / "final.mdl").exists()
    assert live.model_ready(tmp_path, settings) and seen[0].endswith(f"{name}.zip")
    bad = SimpleNamespace(sprache="en", live_modell="", live_mitschrift=True)
    with pytest.raises(OSError):
        live.download_model(tmp_path, bad, urlopen=lambda url, timeout: _Resp(_zip({"../boese.txt": "x"})))
    assert not (tmp_path / "data" / "boese.txt").exists()


def test_drop_turn_only_when_nothing_happened(tmp_path):
    from assistant.providers.base import LLMProvider

    class P:
        drop_turn = LLMProvider.drop_turn

    prov = P()
    prov.messages = [{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Hi"}]
    prov.hit_limit = False
    snap = len(prov.messages)
    prov.messages.append({"role": "user", "content": "Wie wird das Wetter"})
    assert prov.drop_turn(snap, "Wie wird das Wetter") and len(prov.messages) == 2
    prov.messages += [{"role": "user", "content": "Lies a.txt"},
                      {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "x", "input": {}}]}]
    assert not prov.drop_turn(snap, "Lies a.txt") and len(prov.messages) == 4   # Werkzeug lief: bleibt
    assert not prov.drop_turn(snap, "etwas anderes")


def test_live_recognizer_with_fake_vosk(tmp_path):
    class Rec:
        def __init__(self, model, rate):
            self.n = 0

        def AcceptWaveform(self, pcm):  # noqa: N802
            self.n += 1
            return self.n == 2

        def Result(self):  # noqa: N802
            return json.dumps({"text": "hallo nova"})

        def PartialResult(self):  # noqa: N802
            return json.dumps({"partial": "hallo" if self.n == 1 else "wie"})

        def FinalResult(self):  # noqa: N802
            return json.dumps({"text": "wie geht es dir"})

        def Reset(self):  # noqa: N802
            self.n = 0

    fake = SimpleNamespace(SetLogLevel=lambda n: None, Model=lambda p: object(), KaldiRecognizer=Rec)
    rec = live.LiveRecognizer(tmp_path / "m", vosk_module=fake)
    assert rec.feed(b"1") == "hallo"
    assert rec.feed(b"2") == "hallo nova"
    assert rec.feed(b"3") == "hallo nova wie"
    assert rec.finish() == "hallo nova wie geht es dir"
    assert rec.feed(b"1") == "hallo"                               # nach finish frisch


def test_ear_waits_longer_when_the_sentence_obviously_goes_on():
    class Unfinished(FakeRecognizer):
        def feed(self, pcm):
            return "ich moechte gerne und"

        def finish(self):
            return "ich moechte gerne und dann noch was"

    quiet, loud = _block(40), _block(4000)
    # 0,8 s Pause nach "und" (normal reichen 0,6 s) - dann weiter gesprochen
    blocks = [quiet] * 12 + [loud] * 20 + [quiet] * 16 + [loud] * 10 + [quiet] * 30
    seen, _ = _run_ear(blocks, "utterance", pause=0.6, recognizer_factory=Unfinished)
    assert [k for k, _ in seen].count("utterance") == 1 and seen[-1][1].seconds > 2.5


def test_app_texts_get_real_umlauts_but_paths_and_unknown_words_stay():
    from assistant.anzeige import schoen

    assert schoen("Hoeflich, erklaert geduldig, viel Spass") == "H\u00f6flich, erkl\u00e4rt geduldig, viel Spa\u00df"
    assert schoen("Die neue Steuer ist aktuell") == "Die neue Steuer ist aktuell"
    assert schoen(r"C:\Users\fuer\a.txt und pfad/zu/fuer.txt") == r"C:\Users\fuer\a.txt und pfad/zu/fuer.txt"
    assert schoen("Stuetzraeder") == "St\u00fctzr\u00e4der"
    assert schoen("Lies fuer.txt, das ist schoen.") == "Lies fuer.txt, das ist sch\u00f6n."


# -- Fehler aus der Pruefung (Regressionstests) ------------------------------------
class ProgressVoice(FakeVoice):
    """Wie das App-Fenster mit Rueckmeldung pro Satz."""

    def __init__(self):
        super().__init__()
        self.done = 0

    def say(self, text, seq):
        super().say(text, seq)
        self.last = seq

    def finish(self, seq):
        self.done = seq
        if seq >= self.last:
            self._idle = True

    def done_seq(self):
        return self.done


def _ploop():
    host, voice_ = FakeHost(), ProgressVoice()
    return LiveLoop(host, voice_, SETTINGS, ear=FakeEar()), host, voice_


def test_a_cough_after_the_answer_was_streamed_resumes_where_she_was():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Erzaehl was", b"", 1.0))
    step(loop, "text", "Es war einmal ein König. Der hatte drei Töchter, die alle sehr klug waren und viel lasen. "
                       "Eines Tages kam ein Drache in das Land und alle erschraken sehr, auch der König selbst. ")
    step(loop, "turn_end")
    voice_.finish(1)                                   # Satz 1 ist gesagt, Satz 2 laeuft gerade
    step(loop, "barge")
    step(loop, "dropped")                              # war nur ein Husten
    assert voice_.stopped == 1 and host.cancels == []
    assert voice_.said[-1].startswith("Eines Tages") and voice_.said[-2].startswith("Der hatte")
    assert loop.speaking


def test_answering_a_question_by_voice_keeps_the_rest_of_the_answer():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Schreib die Datei", b"", 1.0))
    step(loop, "text", "Klar, mache ich.\n")
    step(loop, "tool")
    host.ask = {"id": "q1", "options": ["einmal", "immer", "nein"]}
    step(loop, "ask", "Neu anlegen: C:\\Spiel\\figuren.py")
    assert "figuren.py" in voice_.said[-1] and "Spiel" not in voice_.said[-1]
    assert voice_.ended                                 # Fenster meldet, wenn die Frage gesagt ist
    step(loop, "barge")                                 # "Ja" waehrend sie noch fragt
    step(loop, "utterance", Utterance("Ja", b"", 0.0))
    assert host.answers == [("q1", "einmal")]
    host.ask = None
    step(loop, "text", "Erledigt, die Datei ist da.")
    step(loop, "turn_end")
    assert voice_.said[-1] == "Erledigt, die Datei ist da."


def test_stop_words_only_as_whole_short_commands():
    for text in ("Was ist der Inhalt", "Wie hoch ist mein Gehalt", "Wo ist die nächste Haltestelle",
                 "Das ist halt so", "Ruf das Wartezimmer an", "Starte die Stoppuhr"):
        assert not live.is_stop(text), text
    for text in ("Stopp!", "Stop", "Hör auf", "Halt", "Warte kurz", "Abbrechen bitte"):
        assert live.is_stop(text), text
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Wo ist die nächste Haltestelle", b"", 1.0))
    assert host.turns == ["Wo ist die nächste Haltestelle"]


def test_nova_does_not_talk_over_you_and_ambiguous_answers_are_asked_again():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Wie wird das Wetter", b"", 1.0))
    step(loop, "onset")                                 # du redest noch weiter ...
    step(loop, "text", "Morgen wird es sonnig. ")
    assert voice_.said == []                            # ... also wartet sie
    step(loop, "dropped")                               # war nichts
    assert voice_.said == ["Morgen wird es sonnig."]
    assert voice_choice("Sag bitte ja, immer oder nein", ["einmal", "immer", "nein"]) is None
    assert voice_choice("Ja, lass mal", ["einmal", "nein"]) == "einmal"


def test_speech_outside_a_turn_finishes_and_novas_own_echo_is_ignored():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Schreib die Datei", b"", 1.0))
    step(loop, "tool")
    host.ask = {"id": "q1", "options": ["einmal", "nein"]}
    step(loop, "ask", "Neu anlegen: figuren.py")
    voice_.finish(1)
    step(loop, "spoken")
    step(loop, "utterance", Utterance("Was meinst du damit", b"", 0.0))
    assert voice_.said[-1] == "Sag bitte ja, immer oder nein." and voice_.ended
    step(loop, "utterance", Utterance("Sag bitte ja immer oder nein", b"", 0.0))   # Echo aus dem Lautsprecher
    assert host.answers == []
    step(loop, "utterance", Utterance("Ja, immer", b"", 0.0))     # genau das, was sie vorschlaegt
    assert host.answers == [("q1", "einmal")] or host.answers == [("q1", "immer")]
    host.ask = None
    voice_.finish(voice_.last)
    step(loop, "spoken")
    assert not loop.speaking and loop.ear.nova[-1] is False


def test_ear_learns_echo_only_from_audible_blocks():
    import random

    random.seed(3)
    quiet = _block(40)
    ear_box = {}

    def run(blocks, nova_from):
        got: queue.Queue = queue.Queue()

        def nova(i):
            if i == nova_from and "ear" in ear_box:
                ear_box["ear"].set_nova_speaking(True)

        ear = Ear(lambda k, d: got.put((k, d)), sd_module=FakeSD(blocks, nova), pause=0.6)
        ear_box["ear"] = ear
        ear.start()
        kinds, end = [], time.monotonic() + 4
        while time.monotonic() < end:
            try:
                kinds.append(got.get(timeout=0.1)[0])
            except queue.Empty:
                if len(kinds) and time.monotonic() > end - 2.5:
                    break
        ear.stop()
        return [k for k in kinds if k != "level"]

    echo = [_block(int(2500 * random.uniform(0.6, 1.4))) for _ in range(60)]
    # Nova sagt etwas, dann 8 s Werkzeug-Arbeit (still), dann spricht sie gleich laut weiter
    assert "barge" not in run([quiet] * 12 + echo[:20] + [quiet] * 160 + echo, nova_from=12)
    # Vorlesen beginnt erst 0,8 s nach dem Satz (langsame Stimme)
    assert "barge" not in run([quiet] * 12 + [quiet] * 16 + echo, nova_from=12)


def test_ear_adapts_when_the_room_gets_louder():
    quiet, fan = _block(40), _block(600)
    seen, _ = _run_ear([quiet] * 20 + [fan] * 300 + [_block(9000)] * 12 + [fan] * 20, "utterance",
                       pause=0.6, max_seconds=40.0)
    utts = [d for k, d in seen if k == "utterance"]
    assert utts[0].seconds < 8                           # nicht 40 s lang "Sprache"


def test_window_voice_reports_each_sentence():
    events = []
    wv = live.WindowVoice(events.append)
    wv.begin(3)
    wv.say("Eins.", 1)
    wv.say("Zwei.", 2)
    wv.spoken(3, 1)
    assert not wv.idle() and wv.done_seq() == 1
    wv.spoken(2, 2)                                      # alte Runde: egal
    assert not wv.idle()
    wv.spoken(3, 2)
    assert wv.idle()


# -- Zweite Pruefung (Regressionstests) -------------------------------------------
def test_not_always_never_means_always():
    opts = ["einmal", "immer", "nein"]
    for text in ("Nicht immer", "Ja, aber nicht immer", "Immer nicht", "Nie immer"):
        assert voice_choice(text, opts) != "immer", text
    assert voice_choice("Ja immer", opts) == "immer" and voice_choice("Immer erlauben", opts) == "immer"
    for text in ("Wann soll ich aufhören", "Was bedeutet Ruhe", "Nicht aufhören", "Stop Motion erklären"):
        assert not live.is_stop(text), text


def test_short_follow_up_after_nova_was_quiet_is_not_taken_for_echo():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Wie wird das Wetter", b"", 0.0))
    step(loop, "text", "Morgen wird es in Berlin sonnig. ")
    step(loop, "turn_end")
    voice_.finish(1)
    step(loop, "spoken")
    loop.quiet_at -= 5                                         # Nova ist seit Sekunden still
    step(loop, "utterance", Utterance("In Berlin?", b"", 0.5))
    assert host.turns[-1] == "In Berlin?"


def test_two_coughs_do_not_repeat_sentences_twice():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Erzaehl was", b"", 0.0))
    step(loop, "text", "Satz eins ist da. Satz zwei kommt jetzt und ist etwas laenger als sechzig Zeichen. "
                       "Satz drei ist der letzte in dieser kleinen Geschichte und auch recht lang. ")
    step(loop, "turn_end")
    voice_.finish(1)
    step(loop, "barge")
    step(loop, "dropped")
    step(loop, "barge")
    step(loop, "dropped")
    tail = voice_.said[3:]
    assert len(tail) == 4 and tail[:2] == tail[2:]             # B, C - und nach dem 2. Husten wieder B, C
    assert [t for t, _ in [(s, 0) for s in tail]].count(tail[0]) == 2


def test_first_cough_of_a_session_keeps_the_answer():
    host = FakeHost()
    wv = live.WindowVoice(lambda e: None)                       # Fenster hat noch nichts gemeldet
    loop = LiveLoop(host, wv, SETTINGS, ear=FakeEar())
    step(loop, "utterance", Utterance("Erzaehl was", b"", 0.0))
    step(loop, "text", "Es war einmal ein König. Der hatte drei Töchter, die alle sehr klug waren und lasen. ")
    step(loop, "turn_end")
    step(loop, "barge")
    step(loop, "dropped")
    assert loop.speaking and wv.sent >= 3                       # lieber wiederholt als verloren


def test_local_voice_counts_per_turn():
    class Spk:
        completed = 0

        def say(self, text):
            pass

        def stop(self):
            pass

        def wait(self, t):
            return False

    spk = Spk()
    lv = live.LocalVoice(spk)
    lv.begin(1)
    for i in (1, 2, 3):
        lv.say("x", i)
    spk.completed = 3
    lv.begin(2)
    lv.say("a", 1)
    assert lv.done_seq() == 0                                   # nicht die 3 der letzten Runde
    spk.completed = 4
    assert lv.done_seq() == 1
    lv.stop()
    assert lv.done_seq() == 1                                   # Stand bleibt nach stop()


def test_second_afterthought_and_stop_then_new_wish():
    loop, host, voice_ = _loop()
    step(loop, "utterance", Utterance("Wie wird das Wetter morgen", b"", 0.0))
    step(loop, "utterance", Utterance("in Berlin", b"", 0.0))
    step(loop, "utterance", Utterance("bitte ausführlich", b"", 0.0))
    assert host.cancels == [True]                               # nicht nochmal (ohne Zuruecknehmen) anhalten
    step(loop, "turn_end", True)
    assert host.turns[-1] == "Wie wird das Wetter morgen in Berlin bitte ausführlich"
    loop2, host2, _ = _loop()
    step(loop2, "utterance", Utterance("Wie wird das Wetter", b"", 0.0))
    step(loop2, "utterance", Utterance("Stopp", b"", 0.0))
    step(loop2, "utterance", Utterance("Erzähl einen Witz", b"", 0.0))
    step(loop2, "turn_end", True)
    assert host2.turns[-1] == "Erzähl einen Witz" and host2.cancels == [False]


def test_while_busy_afterthoughts_are_joined_and_stop_clears():
    loop, host, voice_ = _loop()
    host.is_busy = True
    step(loop, "utterance", Utterance("Wie wird das Wetter morgen", b"", 0.0))
    step(loop, "utterance", Utterance("in Berlin", b"", 0.0))
    host.is_busy = False
    step(loop, "tick") if hasattr(loop, "_on_tick") else loop._tick()
    assert host.turns == ["Wie wird das Wetter morgen in Berlin"]
    loop2, host2, _ = _loop()
    host2.is_busy = True
    step(loop2, "utterance", Utterance("Wie spät ist es", b"", 0.0))
    step(loop2, "utterance", Utterance("Stopp", b"", 0.0))
    host2.is_busy = False
    loop2._tick()
    assert host2.turns == []


def test_onset_while_nova_speaks_counts_as_interruption_and_exit_works_during_a_question():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Wie wird das Wetter", b"", 0.0))
    step(loop, "text", "Morgen wird es sonnig. ")
    step(loop, "onset")
    assert voice_.stopped == 1 and not loop.speaking
    loop2, host2, _ = _ploop()
    step(loop2, "utterance", Utterance("Schreib die Datei", b"", 0.0))
    step(loop2, "tool")
    host2.ask = {"id": "q1", "options": ["einmal", "nein"]}
    step(loop2, "ask", "Neu anlegen: a.txt")
    step(loop2, "utterance", Utterance("Chat-Modus", b"", 0.0))
    assert loop2.stop_event.is_set()


def test_question_asked_while_you_talk_is_not_answered_by_that_sentence():
    loop, host, voice_ = _ploop()
    step(loop, "utterance", Utterance("Räum die Fotos auf", b"", 0.0))
    step(loop, "tool")
    step(loop, "onset")                                         # du redest schon
    host.ask = {"id": "q1", "options": ["einmal", "nein"]}
    step(loop, "ask", "Löschen: C:\\Daten\\Fotos (312 Dateien)")
    step(loop, "utterance", Utterance("Ja und mach danach noch Musik an", b"", 2.0))
    assert host.answers == []                                   # die Frage hattest du noch nicht gehoert
    assert "Fotos" in voice_.said[-1]                           # jetzt wird sie vorgelesen


def test_long_even_speech_is_not_cut_by_the_rising_noise_floor():
    import random

    random.seed(1)
    quiet = _block(40)
    speech = [_block(random.randint(2000, 4000)) if random.random() > 0.05 else quiet for _ in range(200)]
    seen, _ = _run_ear([quiet] * 12 + speech + [quiet] * 16, "utterance", pause=0.6, max_seconds=40.0)
    assert [d for k, d in seen if k == "utterance"][0].seconds > 9.5


def test_stop_button_counts_as_you_being_there():
    from assistant.live import LiveLoop

    class Host:
        def event(self, e): pass
        def busy(self): return False

    class Voice:
        def idle(self): return True
        def stop(self): pass

    class Ear:
        live = True
        def start(self): pass
        def stop(self): pass

    loop = LiveLoop(Host(), Voice(), SimpleNamespace(pause=0.6, unterbrechen=True), ear=Ear())
    before = loop.spoke
    loop._on_hush(None)
    assert loop.spoke == before + 1


def _goodbye_loop():
    from assistant.live import LiveLoop

    class Host:
        def __init__(self):
            self.answers, self.cancelled = [], 0
            self.ask = None

        def event(self, e): pass
        def busy(self): return False
        def is_exit(self, text): return False
        def pending_ask(self): return self.ask
        def answer_ask(self, ask_id, value): self.answers.append((ask_id, value))
        def cancel_turn(self, drop): self.cancelled += 1

        def start_turn(self, text):
            self.sent = text
            return True

    class Voice:
        def idle(self): return True
        def stop(self): pass
        def say(self, *a): pass
        def begin(self, *a): pass

    class Ear:
        live = True
        def start(self): pass
        def stop(self): pass
        def set_nova_speaking(self, v): pass

    host = Host()
    loop = LiveLoop(host, Voice(), SimpleNamespace(pause=0.6, unterbrechen=True), ear=Ear())
    return loop, host


def test_yes_goodbye_answers_the_question_first_then_leaves():
    from assistant.live import Utterance

    loop, host = _goodbye_loop()
    host.ask = {"id": "q1", "options": ["einmal", "immer", "nein"]}
    loop.ask_text = "Neu anlegen?"
    loop.ask_said_at = time.monotonic() - 2
    loop._on_utterance(Utterance("Ja, tschüss", b"", 0.5))
    assert host.answers and host.answers[0][1] == "einmal"
    assert loop.stop_event.is_set() and loop.exit_reason == "bye"


def test_goodbye_during_an_answer_lets_the_request_finish():
    loop, host = _goodbye_loop()
    loop.turn_active = True
    loop.exit_reason = "bye"
    loop.stop_event.set()
    loop.run()
    assert host.cancelled == 0  # die Bitte wird noch erledigt
    loop, host = _goodbye_loop()
    loop.turn_active = True
    loop.exit_reason = "chat"
    loop.stop_event.set()
    loop.run()
    assert host.cancelled == 1


def test_novas_own_ciao_is_an_echo_and_bis_morgen_answers_a_question():
    from assistant.live import Utterance, is_goodbye

    loop, host = _goodbye_loop()
    loop.recent.append((time.monotonic(), {"auf", "italienisch", "sagt", "man", "ciao"}))
    assert loop._is_echo("Ciao")
    assert not loop._is_echo("Tschüss")
    assert is_goodbye("Bis morgen") and not is_goodbye("Bis morgen", after_question=True)
    loop.last_said = (time.monotonic(), "Bis wann brauchst du die Zusammenfassung?")
    loop._on_utterance(Utterance("Bis morgen", b"", 0.5))
    assert not loop.stop_event.is_set() and host.sent == "Bis morgen"  # geht als Antwort an die KI
