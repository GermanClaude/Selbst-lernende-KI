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


def test_claude_strict_tools_have_at_most_24_optional_params():
    from assistant.tools import build_registry
    from assistant.tools.base import MAX_OPTIONAL, zaehle_optionale

    specs = build_registry().specs()
    optional = sum(zaehle_optionale(s["input_schema"]) for s in specs if s.get("strict"))
    assert optional <= MAX_OPTIONAL == 24
    assert specs == build_registry().specs()  # stabil (Prompt-Cache)


def test_limits_hold_even_with_many_tools():
    from assistant.tools.base import MAX_OPTIONAL, MAX_STRIKT, grenzen_einhalten, zaehle_optionale

    def spec(name, opt):
        props = {f"p{i}": {"type": "string"} for i in range(opt + 1)}
        return {"name": name, "input_schema": {"type": "object", "properties": props,
                                               "required": ["p0"]}, "strict": True}

    specs = grenzen_einhalten([spec(f"w{i:02d}", i % 4) for i in range(30)] + [spec("shell_befehl", 2)])
    strikt = [s for s in specs if s.get("strict")]
    assert len(strikt) <= MAX_STRIKT
    assert sum(zaehle_optionale(s["input_schema"]) for s in strikt) <= MAX_OPTIONAL
    assert any(s["name"] == "shell_befehl" for s in strikt)


def test_optional_params_counted_in_nested_schemas():
    from assistant.tools.base import zaehle_optionale

    schema = {"type": "object", "required": ["a"], "properties": {
        "a": {"type": "array", "items": {"type": "object", "required": [],
                                         "properties": {"x": {"type": "string"}}}},
        "b": {"type": "string"}}}
    assert zaehle_optionale(schema) == 2  # b und x


def test_claude_retries_without_strict_when_schema_rejected():
    from assistant.providers.anthropic_provider import AnthropicProvider

    class Fehler(Exception):
        status_code = 400
        message = "Schemas contains too many optional parameters (26) (limit: 24)"

    assert AnthropicProvider._schema_abgelehnt(Fehler())
    andere = Fehler()
    andere.message = "prompt is too long"
    assert not AnthropicProvider._schema_abgelehnt(andere)
