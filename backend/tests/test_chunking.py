import pytest

from app.services.chunking import chunk_text, normalize_text


def test_short_text_is_a_single_chunk():
    assert chunk_text("Refunds are available within 30 days.") == ["Refunds are available within 30 days."]


def test_paragraphs_are_packed_up_to_chunk_size():
    paragraphs = [f"Paragraph {i} " + "word " * 30 for i in range(10)]
    chunks = chunk_text("\n\n".join(paragraphs), chunk_size=400, overlap=0)

    assert len(chunks) > 1
    assert all(len(chunk) <= 400 for chunk in chunks)
    # With no overlap, every paragraph appears exactly once and in order.
    joined = "\n\n".join(chunks)
    assert [p.strip() for p in joined.split("\n\n")] == [p.strip() for p in paragraphs]


def test_long_paragraph_is_split_on_sentences():
    sentences = [f"Sentence number {i} explains one detail of the policy." for i in range(40)]
    chunks = chunk_text(" ".join(sentences), chunk_size=300, overlap=0)

    assert all(len(chunk) <= 300 for chunk in chunks)
    assert all(chunk.endswith(".") for chunk in chunks), "chunks should end on sentence boundaries"


def test_overlap_repeats_trailing_context():
    sentences = [f"Fact {i} is important." for i in range(60)]
    chunks = chunk_text(" ".join(sentences), chunk_size=200, overlap=60)

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        first_sentence_of_current = current.split(". ")[0]
        last_sentence_of_previous = previous.rsplit(". ", 1)[-1]
        assert first_sentence_of_current in previous, "next chunk should start inside the previous one"
        assert last_sentence_of_previous in current, "boundary sentence should appear in both chunks"


def test_unbreakable_token_is_hard_wrapped():
    chunks = chunk_text("x" * 2_000, chunk_size=500, overlap=0)

    assert [len(c) for c in chunks] == [500, 500, 500, 500]


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a  \t b\r\n\r\n\r\n\r\nc  ") == "a b\n\nc"


@pytest.mark.parametrize("size, overlap", [(0, 0), (100, 100), (100, -1)])
def test_invalid_parameters_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=size, overlap=overlap)
