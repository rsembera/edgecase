"""A note too long for the model's context goes through the Scribe in sections.

Bug (Nov 2026, production): a long session note came back cut off
mid-sentence with "Result Is Incomplete". The model's context on a 16 GB
Mac is 4096 tokens, and the note plus its rewritten copy did not fit. A
larger context costs memory the machine does not have, so a note that does
not fit is now split at paragraph breaks, each section is processed with
the unchanged prompts, and the results are streamed back joined by the
original breaks. A note that fits still goes through in one pass.

The stand-in model counts one token per word and echoes the notes it was
given, padded with newlines, so the tests can see exactly what was sent and
that nothing was lost or reordered. No real model is loaded.
"""
import json
import re

import pytest

import ai.assistant as assistant
from ai.sections import section_budget, split_into_sections

N_CTX = 4096


def _words(text):
    return len(text.split())


class _EchoLlm:
    """Echoes the NOTES block of the prompt. One token per word."""

    def __init__(self, cut_call=None):
        self.calls = []          # (prompt_tokens, notes) per call
        self.cut_call = cut_call  # 1-based call that stops for length

    def n_ctx(self):
        return N_CTX

    def tokenize(self, data, *args, **kwargs):
        return data.decode().split()

    def create_chat_completion(self, messages, **kwargs):
        user = messages[-1]["content"]
        notes = re.search(r"NOTES:\n(.*)\n\n[A-Z ]+:$", user, re.S).group(1)
        self.calls.append((sum(_words(m["content"]) for m in messages), notes))
        cut = self.cut_call == len(self.calls)
        pieces = re.findall(r"\s+|\S+", notes)
        if cut:
            pieces = pieces[:len(pieces) // 2]
        yield {"choices": [{"delta": {"content": "\n"}, "finish_reason": None}]}
        for p in pieces:
            yield {"choices": [{"delta": {"content": p}, "finish_reason": None}]}
        yield {"choices": [{"delta": {"content": "\n\n"}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "length" if cut else "stop"}]}


def _note(paragraphs, words_each=60):
    return "\n\n".join(
        " ".join(f"p{p}w{w}" for w in range(words_each - 1)) + f" end{p}."
        for p in range(paragraphs))


def _run(client, monkeypatch, text, action="proofread", cut_call=None):
    llm = _EchoLlm(cut_call)
    monkeypatch.setattr(assistant, "_llm", llm)
    monkeypatch.setattr(assistant, "_model_loaded", True)
    resp = client.post("/api/ai/process", json={"action": action, "text": text})
    events = [json.loads(line[6:]) for line in resp.get_data(as_text=True).splitlines()
              if line.startswith("data: ")]
    return llm, events, "".join(e.get("token", "") for e in events)


# -- the route ---------------------------------------------------------------

def test_long_note_is_processed_in_sections_that_each_fit(client, app_db, monkeypatch):
    note = _note(50)                       # 3000 words: cannot fit twice in 4096
    llm, events, out = _run(client, monkeypatch, note)

    assert len(llm.calls) > 1, "the whole note was sent to the model in one pass"
    for prompt_tokens, notes in llm.calls:
        # Room for the prompt and for a copy of the section as output.
        assert prompt_tokens + _words(notes) <= N_CTX
    assert out == note, "sections must come back in order, joined by the original breaks"
    assert events[-1] == {"done": True, "truncated": False}


def test_sections_break_only_at_paragraph_breaks_when_paragraphs_fit(client, app_db, monkeypatch):
    note = _note(50)
    llm, _, _ = _run(client, monkeypatch, note)
    paragraphs = note.split("\n\n")
    sent = [p for _, notes in llm.calls for p in notes.split("\n\n")]
    assert sent == paragraphs


def test_note_that_fits_is_one_pass_and_unchanged(client, app_db, monkeypatch):
    note = _note(10)                       # 600 words
    llm, events, out = _run(client, monkeypatch, note)
    assert len(llm.calls) == 1 and llm.calls[0][1] == note
    # One pass streams the model's tokens exactly as before, padding and all.
    assert out == "\n" + note + "\n\n"


def test_a_section_cut_short_stops_there_and_is_flagged(client, app_db, monkeypatch):
    note = _note(50)
    llm, events, out = _run(client, monkeypatch, note, cut_call=1)
    assert len(llm.calls) == 1, "later sections after a cut would hide the gap mid-note"
    assert events[-1] == {"done": True, "truncated": True}
    assert note.startswith(out) and out != note


@pytest.mark.parametrize("action", ["writeup", "expand", "condense"])
def test_every_action_sections_a_long_note(client, app_db, monkeypatch, action):
    note = _note(50)
    llm, events, out = _run(client, monkeypatch, note, action=action)
    assert len(llm.calls) > 1 and out == note
    assert events[-1] == {"done": True, "truncated": False}


# -- the splitter ------------------------------------------------------------

def _rejoin(sections):
    return "".join(text + sep for text, sep in sections)


def test_split_loses_nothing_and_respects_the_budget():
    note = _note(40)
    sections = split_into_sections(note, 500, _words)
    assert len(sections) > 1 and sections[-1][1] == ""
    assert _rejoin(sections) == note
    assert all(_words(text) <= 500 for text, _ in sections)


def test_split_falls_back_to_lines_then_sentences_then_words():
    lines = "\n".join(f"- point {i} " + "word " * 30 for i in range(20)).strip()
    sentences = " ".join(f"Sentence {i} " + "word " * 30 + "end." for i in range(20))
    run_on = " ".join(f"w{i}" for i in range(700))
    for text in (lines, sentences, run_on):
        sections = split_into_sections(text, 200, _words)
        assert len(sections) > 1
        assert _rejoin(sections) == text
        assert all(_words(t) <= 200 for t, _ in sections)
    assert all("\n" in sep for _, sep in split_into_sections(lines, 200, _words)[:-1])


def test_sections_are_balanced_not_one_full_and_one_scrap():
    note = _note(21, words_each=50)        # 1050 words, budget 1000
    sizes = [_words(t) for t, _ in split_into_sections(note, 1000, _words)]
    assert len(sizes) == 2 and min(sizes) >= 450


def test_text_within_budget_is_one_section():
    assert split_into_sections("Short note.\n\nTwo paragraphs.", 100, _words) == [
        ("Short note.\n\nTwo paragraphs.", "")]


def test_budget_leaves_room_for_prompt_and_output():
    for action in ("proofread", "writeup", "expand", "condense"):
        budget = section_budget(action, n_ctx=4096, max_tokens=2048, overhead=500)
        assert 0 < budget < (4096 - 500) / 2
    # Expand writes more than it reads, so it takes smaller sections.
    assert (section_budget("expand", 4096, 2048, 500)
            < section_budget("proofread", 4096, 2048, 500))
