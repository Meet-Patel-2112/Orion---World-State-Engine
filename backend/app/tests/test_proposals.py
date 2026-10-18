"""Re-extraction proposals (docs/api.md §17): a chapter edit compares, it doesn't write, and lists what would change."""
from app.api.deps import get_current_user
from app.config.settings import settings
from app.main import app
from app.models.user import User
from app.services.proposal_service import ProposalService
from app.tests.test_phase1_api import _manuscript, api  # noqa: F401  (fixture)


def _upload_and_edit(env, world_id, client, monkeypatch):
    env.install_fake_extractor()
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "background")
    app.dependency_overrides[get_current_user] = lambda: User(id="u-phase1", email="phase1@example.com")
    upload = client.post(f"/api/v1/worlds/{world_id}/manuscripts",
                         files={"file": ("book.txt", _manuscript(2), "text/plain")})
    runs = env.runs_by_chapter(upload.json()["job_id"])
    before = env.world_rows(world_id)
    edit = client.put(f"/api/v1/worlds/{world_id}/chapters/{runs[2]['chapter_id']}",
                      json={"content": "Chapter 2: T2 edited\nAlice ran. [A]"})
    return upload.json()["job_id"], edit.json()["job_id"], runs, before


def test_an_unchanged_chapter_proposes_only_known_items_and_writes_nothing(api, monkeypatch):
    env, world_id, client = api
    initial_job, job_id, runs, before = _upload_and_edit(env, world_id, client, monkeypatch)

    resp = client.get(f"/api/v1/jobs/{job_id}/proposals")

    assert resp.status_code == 200 and resp.json()["status"] == "ready"
    body = resp.json()
    assert body["chapter_id"] == runs[2]["chapter_id"] and body["chapter_number"] == 2
    assert {p["change"] for p in body["proposals"]} == {"known"}            # same chapter, same claims
    assert env.world_rows(world_id) == before                               # nothing was written
    assert client.get(f"/api/v1/jobs/{initial_job}/proposals").status_code == 404   # first upload writes directly


def test_new_and_changed_claims_point_at_stored_or_proposed_entities(api, monkeypatch):
    env, world_id, client = api
    _, job_id, runs, _ = _upload_and_edit(env, world_id, client, monkeypatch)
    extraction = {"entities": [
        {"canonical_name": "HeroAC", "type": "character", "aliases": ["Ace"], "attributes": {"age": "99"}},
        {"canonical_name": "Newbie Quill", "type": "character", "aliases": ["Newbie"], "attributes": {"age": "7"}}],
        "relationships": [{"subject": "Newbie", "predicate": "SIBLING_OF", "object": "HeroAC"},
                          {"subject": "HeroAC", "predicate": "FRIEND_OF", "object": "SharedA"}],
        "events": [{"id": "e9", "type": "MEETING", "evidence": "Newbie met HeroAC",
                    "participants": [{"name": "Newbie Quill", "role": "AGENT"}, "HeroAC"]}]}

    with env.Session() as s:
        result = ProposalService(s).build(world_id, job_id, runs[2]["chapter_id"], 2, extraction)
    by = {(p["kind"], p["summary"]): p for p in result["proposals"]}

    hero, newbie = by[("entity", "Known character: HeroAC")], by[("entity", "New character: Newbie Quill")]
    assert hero["change"] == "known" and hero["match_entity_id"]
    assert newbie["change"] == "new" and newbie["match_entity_id"] is None
    alias = by[("alias", "HeroAC is also called Ace")]
    assert alias["entity_id"] == hero["match_entity_id"] and alias["proposed"] == {"alias": "Ace"}
    age = by[("fact", "HeroAC age: 32 → 99")]
    assert age["change"] == "changed" and age["current"]["value"] == "32" and age["proposed"]["value"] == "99"
    assert by[("fact", "Newbie Quill age: 7")]["entity"] == {"entity_ref": newbie["id"]}
    sibling = by[("relationship", "Newbie SIBLING_OF HeroAC")]
    assert sibling["change"] == "new" and sibling["source"] == {"entity_ref": newbie["id"]}
    assert sibling["target"] == {"entity_id": hero["match_entity_id"]}
    friend = by[("relationship", "HeroAC KNOWS → FRIEND_OF SharedA")]
    assert friend["change"] == "changed" and friend["current"]["relationship_type"] == "KNOWS"
    [event] = [p for p in result["proposals"] if p["kind"] == "event"]
    assert event["change"] == "new" and [x["entity"] for x in event["participants"]] == [
        {"entity_ref": newbie["id"]}, {"entity_id": hero["match_entity_id"]}]
