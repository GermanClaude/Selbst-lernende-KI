from assistant.memory import Memory


def test_remember_and_recall(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    fid = m.remember("mag Tee lieber als Kaffee", category="vorliebe", importance=4)
    assert fid > 0
    results = m.search("Tee")
    assert any("Tee" in f.content for f in results)
    m.close()


def test_dedup_updates_instead_of_duplicating(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    a = m.remember("gleicher inhalt", importance=2)
    b = m.remember("gleicher inhalt", importance=5)
    assert a == b
    assert m.count_facts() == 1
    assert m.top_facts()[0].importance == 5
    m.close()


def test_forget(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    fid = m.remember("etwas")
    assert m.forget(fid) is True
    assert m.forget(99999) is False
    assert m.count_facts() == 0
    m.close()


def test_importance_is_clamped(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    fid = m.remember("x", importance=99)
    assert m.top_facts()[0].importance == 5
    fid2 = m.remember("y", importance=-3)
    assert [f.importance for f in m.top_facts() if f.id == fid2][0] == 1
    m.close()


def test_context_block_and_episodes(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    assert "Noch nichts" in m.context_block()
    m.remember("Projektordner ist /home/projekte", category="projekt", importance=5)
    m.add_episode("Wir haben ueber das Setup gesprochen.")
    block = m.context_block()
    assert "Projektordner" in block
    assert "Setup" in block
    assert m.recent_episodes()[0] == "Wir haben ueber das Setup gesprochen."
    m.close()


def test_empty_content_rejected(tmp_path):
    m = Memory(tmp_path / "m.sqlite3")
    try:
        m.remember("   ")
        assert False, "sollte ValueError werfen"
    except ValueError:
        pass
    m.close()
