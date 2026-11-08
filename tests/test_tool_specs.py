from assistant.tools import build_registry


def test_openai_specs_shape():
    reg = build_registry()
    specs = reg.specs_openai()
    assert specs, "es sollte Werkzeuge geben"
    for s in specs:
        assert s["type"] == "function"
        fn = s["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        assert fn["parameters"]["type"] == "object"


def test_anthropic_and_openai_have_same_tool_names():
    reg = build_registry()
    anthro = {s["name"] for s in reg.specs()}
    openai = {s["function"]["name"] for s in reg.specs_openai()}
    assert anthro == openai


def test_specs_are_sorted_stable():
    reg = build_registry()
    names = [s["function"]["name"] for s in reg.specs_openai()]
    assert names == sorted(names)


def test_claude_gets_at_most_20_strict_tools():
    from assistant.tools import build_registry
    from assistant.tools.base import MAX_STRIKT

    specs = build_registry().specs()
    assert sum(1 for s in specs if s.get("strict")) <= MAX_STRIKT == 20
    assert specs == build_registry().specs()  # stabil (Prompt-Cache)
    wichtig = {s["name"]: s.get("strict") for s in specs}
    assert wichtig["datei_schreiben"] and wichtig["shell_befehl"]  # Wichtige bleiben strikt
