import pytest

from guardbank.rag.corpus import chunk_docs, load_corpus
from guardbank.rag.embed import HashingEmbedder
from guardbank.rag.retriever import Retriever


@pytest.fixture(scope="module")
def retriever():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    chunks = chunk_docs(load_corpus(root / "data" / "corpus"))
    return Retriever(chunks, HashingEmbedder(), top_k=4)


def test_returns_top_k_unique_chunks(retriever):
    hits = retriever.search("What is the ATM withdrawal limit per day?")
    assert len(hits) == 4
    assert len({h.chunk.id for h in hits}) == 4
    assert hits[0].score >= hits[-1].score


@pytest.mark.parametrize(
    ("query", "doc_id"),
    [
        ("What is the daily ATM cash withdrawal limit?", "atm-cards"),
        ("How do I block my lost debit card?", "card-blocking"),
        ("What documents do I need for KYC?", "kyc-requirements"),
        ("What is the interest rate on a fixed deposit?", "fixed-deposits"),
    ],
)
def test_relevant_doc_ranks_first(retriever, query, doc_id):
    assert retriever.search(query)[0].chunk.doc_id == doc_id


@pytest.mark.slow
def test_sentence_transformer_embedder_ranks_fee_doc():
    from pathlib import Path

    from guardbank.rag.embed import SentenceTransformerEmbedder

    root = Path(__file__).resolve().parents[2]
    chunks = chunk_docs(load_corpus(root / "data" / "corpus"))
    r = Retriever(chunks, SentenceTransformerEmbedder("BAAI/bge-small-en-v1.5"), top_k=4)
    assert r.search("how much does a cheque book cost")[0].chunk.doc_id == "service-fees"
