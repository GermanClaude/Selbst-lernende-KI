"""Gefaelschte SDK-Clients fuer Tests (kein echter Netzzugriff/Schluessel noetig)."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace


def dump(value) -> str:
    """Anfrage so serialisieren, wie sie verschickt wuerde (fuer "byte-gleich"-Vergleiche).
    SDK-Bloecke der Fakes (SimpleNamespace) werden wie dicts geschrieben."""
    return json.dumps(value, default=lambda o: getattr(o, "__dict__", None) or repr(o), ensure_ascii=False)


# ----- Anthropic ----------------------------------------------------------
class AnthroStream:
    def __init__(self, message, events):
        self._message = message
        self._events = events

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._message


class AnthroMessages:
    """scripted: Liste von (Nachricht, Ereignisse) - oder eine Exception, die geworfen wird."""

    def __init__(self, scripted):
        self._scripted = scripted
        self.calls = 0
        self.requests = []  # je Anfrage: so wurde 'messages' verschickt (serialisiert)

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        self.requests.append(dump(kwargs.get("messages")))
        item = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        msg, events = item
        return AnthroStream(msg, events)

    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="zusammenfassung")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


class AnthroClient:
    def __init__(self, scripted):
        self.messages = AnthroMessages(scripted)


def anthro_msg(blocks, stop_reason="end_turn", stop_details=None, usage=None):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        stop_details=stop_details,
        usage=usage
        or SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name, tid, tinput):
    return SimpleNamespace(type="tool_use", name=name, id=tid, input=tinput)


# ----- DeepSeek (OpenAI-kompatibel) ---------------------------------------
def ds_text_chunk(text):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def ds_toolcall_chunk(index, tid=None, name=None, args_fragment=None):
    fn = SimpleNamespace(name=name, arguments=args_fragment)
    tc = SimpleNamespace(index=index, id=tid, function=fn)
    delta = SimpleNamespace(content=None, tool_calls=[tc])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def ds_usage_chunk(prompt=100, completion=50, cache_hit=0, cache_miss=None):
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_cache_hit_tokens=cache_hit,
        prompt_cache_miss_tokens=(prompt - cache_hit) if cache_miss is None else cache_miss,
    )
    return SimpleNamespace(choices=[], usage=usage)


def ds_reply(content="zusammenfassung", prompt=10, completion=5):
    """Antwort auf eine nicht gestreamte Anfrage (Zusammenfassung, Bildbeschreibung)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt, completion_tokens=completion,
            prompt_cache_hit_tokens=0, prompt_cache_miss_tokens=prompt,
        ),
    )


class DSCompletions:
    """scripted_streams: Liste von Chunk-Listen - oder eine Exception, die geworfen wird.
    non_stream: optional, (**kwargs) -> Antwort fuer nicht gestreamte Anfragen (darf werfen)."""

    def __init__(self, scripted_streams, non_stream=None):
        self._scripted = scripted_streams
        self.non_stream = non_stream
        self.calls = 0
        self.last_kwargs = None        # letzte gestreamte Anfrage
        self.requests = []             # je gestreamter Anfrage: Kopie von 'messages'
        self.non_stream_calls = []     # alle nicht gestreamten Anfragen (kwargs)

    def create(self, **kwargs):
        if not kwargs.get("stream", False):
            # Zusammenfassung / Bildbeschreibung (nicht gestreamt).
            self.non_stream_calls.append(kwargs)
            if self.non_stream is not None:
                return self.non_stream(**kwargs)
            return ds_reply()
        self.last_kwargs = kwargs
        self.requests.append(copy.deepcopy(kwargs.get("messages")))
        item = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        return iter(item)


class DSChat:
    def __init__(self, scripted_streams, non_stream=None):
        self.completions = DSCompletions(scripted_streams, non_stream)


class DSClient:
    def __init__(self, scripted_streams, non_stream=None):
        self.chat = DSChat(scripted_streams, non_stream)
