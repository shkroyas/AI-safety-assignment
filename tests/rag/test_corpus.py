from guardbank.rag.corpus import load_corpus


def test_corpus_has_20_normal_and_3_poisoned(root):
    docs = load_corpus(root / "data" / "corpus")
    assert sum(not d.poisoned for d in docs) == 20
    assert sum(d.poisoned for d in docs) == 3


def test_docs_have_front_matter_and_reasonable_length(root):
    for d in load_corpus(root / "data" / "corpus"):
        assert d.id and d.title and d.topic
        words = len(d.body.split())
        assert 100 <= words <= 450, (d.id, words)


def test_doc_ids_unique(root):
    ids = [d.id for d in load_corpus(root / "data" / "corpus")]
    assert len(ids) == len(set(ids))


def test_chunks_split_by_section(root):
    from guardbank.rag.corpus import chunk_docs

    docs = load_corpus(root / "data" / "corpus")
    chunks = chunk_docs(docs)
    assert len(chunks) > len(docs)
    assert all(c.id.startswith(c.doc_id + "#") for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
