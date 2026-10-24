import pytest

from app.services.llm import ContextPassage
from app.services.prompts import NO_ANSWER, build_prompt, is_degenerate, is_no_answer


@pytest.mark.parametrize(
    "answer",
    [
        NO_ANSWER,
        "I couldn't find information about the office WiFi password in the provided context passages.",
        "I could not find anything about that topic.",
        "No information about this is available in the passages.",
    ],
)
def test_declines_are_detected(answer):
    assert is_no_answer(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "You have 30 days from the purchase date to request a refund [1].",
        "If the VPN client couldn't find the server, restart it and check the network [1].",
    ],
)
def test_real_answers_are_not_treated_as_declines(answer):
    assert not is_no_answer(answer)


@pytest.mark.parametrize("answer, expected", [
    ("[1] (Source: Refund Policy)", True),
    ("[1][2]", True),
    ("You have 30 days to request a refund [1].", False),
])
def test_degenerate_replies_are_detected(answer, expected):
    assert is_degenerate(answer) is expected


def test_prompt_ends_with_an_answer_cue():
    prompt = build_prompt("refund policy", [ContextPassage(1, "Refund Policy", "30 days.")])

    assert prompt.user.endswith("Answer (in full sentences, citing passages like [1]):")
