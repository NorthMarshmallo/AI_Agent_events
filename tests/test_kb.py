from events_agent import kb


class FakeClient:
    def __init__(self, names):
        self.names, self.created, self.dropped = set(names), [], []

    def has_collection(self, name):
        return name in self.names

    def list_collections(self):
        return sorted(self.names)

    def drop_collection(self, name):
        self.names.discard(name)
        self.dropped.append(name)


CHUNKS = [{"page": "P", "section": "", "url": "", "text": "a long enough line about an event of the year 2026"}]


def test_chunk_lines_keeps_sections_and_skips_short_lines():
    page = {"page": "P", "url": "u", "text": "== March ==\nshort\n" + CHUNKS[0]["text"]}
    assert kb.chunk_lines(page) == [{**CHUNKS[0], "section": "March", "url": "u"}]


def test_collection_name_depends_on_data_and_label():
    name = kb.collection_name(CHUNKS, "eval")
    assert name == kb.collection_name(CHUNKS, "eval") and name.startswith("kb_eval_")
    assert name != kb.collection_name(CHUNKS, "full")
    assert name != kb.collection_name([{**CHUNKS[0], "text": CHUNKS[0]["text"] + "!"}], "eval")


def test_existing_base_is_reused_and_old_versions_dropped():
    name = kb.collection_name(CHUNKS, "eval")
    client = FakeClient([name, "kb_eval_old", "kb_full_other", "facts"])
    kb.KnowledgeBase(client, CHUNKS, "eval", vectors=object())     # коллекция есть: векторы не нужны, загрузки нет
    assert client.dropped == ["kb_eval_old"]
    assert client.names == {name, "kb_full_other", "facts"}


def test_all_corpus_vectors_are_cached():
    chunks = kb.corpus_chunks()
    vectors = kb.Vectors()
    assert all(kb.key_of(kb.emb_text(c)) in vectors.vectors for c in chunks)
