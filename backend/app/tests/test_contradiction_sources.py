"""Contradictions point at the line that caused them, and one the author rejected is not raised again."""
from app.models.contradiction import Contradiction
from app.services.chapter_service import ChapterService
from app.services.contradiction_sources import sources_for
from app.tests.test_phase2_integration import chapter_data, contradictions, integrate, person, world  # noqa: F401

TEXTS = {1: "Chapter 1: Title 1\nAlice Sterling walked to Silver Haven.\nAlice had blue eyes, like her father.",
         2: "Chapter 2: Title 2\nThe rain fell.\nWhen she turned, Alice's eyes were green in the lamplight.",
         3: "Chapter 3: Title 3\nAlice's green eyes narrowed.",
         4: "Chapter 4: Title 4\nAlice's brown eyes narrowed."}


def _write(env, w, n):
    with env.Session() as s:
        ChapterService(s).update_chapter_content(w["runs"][n]["chapter_id"], TEXTS[n])


def _eyes(env, w, n, colour):
    _write(env, w, n)
    integrate(env, w["world_id"], w["runs"][n], chapter_data([person("Alice Sterling", eye_color=colour)]))


def test_each_side_points_at_its_chapter_line_and_words(world):
    env, w = world
    _eyes(env, w, 1, "blue")
    _eyes(env, w, 2, "green")

    [c] = contradictions(env, w["world_id"])
    with env.Session() as s:
        old, new = sources_for(s, s.get(Contradiction, c["id"]))
    assert (old["side"], old["label"], old["highlight"], old["chapter_id"]) == (
        "old", "Chapter 1 · line 3", "blue", w["runs"][1]["chapter_id"])
    assert TEXTS[1][old["start"]:old["end"]] == "blue" and old["snippet"] == "Alice had blue eyes, like her father."
    assert (new["label"], new["highlight"]) == ("Chapter 2 · line 3", "green")
    assert new["snippet"] == "When she turned, Alice's eyes were green in the lamplight."


def test_a_rejected_contradiction_is_not_raised_again_but_a_new_value_is(world):
    env, w = world
    _eyes(env, w, 1, "blue")
    _eyes(env, w, 2, "green")
    with env.Session() as s:
        s.get(Contradiction, contradictions(env, w["world_id"])[0]["id"]).status = "DISMISSED"   # the author declined it
        s.commit()

    _eyes(env, w, 3, "green")                       # the same blue/green claim from a later chapter
    assert [c["status"] for c in contradictions(env, w["world_id"])] == ["DISMISSED"]

    w["runs"][4] = w["runs"][3]                      # a third colour is a different claim
    _eyes(env, w, 4, "brown")
    assert sorted(c["status"] for c in contradictions(env, w["world_id"])) == ["DETECTED", "DISMISSED"]
