"""
Re-extraction proposals (docs/api.md §17): compare a chapter's fresh extraction with the current world and list what
would change, without writing to the world tables. The author applies what they accept through the manual endpoints,
so the world state they have edited and accepted stays the truth until they say otherwise (RULES.md 3.4).

Proposals are stored as a JSON file keyed by job id (no schema change, SPLIT.md Rule S.1).
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.contracts.normalization import normalize_entity_name
from app.models.event import Event
from app.models.fact import Fact
from app.models.relationship import Relationship
from app.pipeline.resolution.fact_resolution import compare_fact_values
from app.services.world_state_service import WorldStateService

# Read the same in both directions, so an existing B -> A edge is the A -> B the extractor proposes
SYMMETRIC = {"FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "MARRIED_TO", "ALLY_OF", "KNOWS", "RELATED_TO", "ENGAGED_TO"}
CONFIDENCE = 1.0          # the extractor gives no per-claim score; integration stores 1.0 too


def proposals_path(job_id: str) -> Path:
    return Path(settings.STORAGE_DIR) / "proposals" / f"{job_id}.json"


def load_proposals(job_id: str) -> Optional[Dict[str, Any]]:
    path = proposals_path(job_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class ProposalService:
    def __init__(self, db: Session):
        self.db = db
        self.world = WorldStateService(db)

    def _match(self, world_id: str, name: str, aliases: List[str], entity_type: Optional[str]):
        exact = self.world.entity_repo.get_by_canonical(world_id, name)    # "Mr. Bennet's wife" is no proper name
        return exact or self.world.find_entity(world_id, [name, *aliases], entity_type)

    def build(self, world_id: str, job_id: str, chapter_id: str, chapter_number: int,
              extraction: Dict[str, Any]) -> Dict[str, Any]:
        proposals: List[Dict[str, Any]] = []
        ref_of: Dict[str, Dict[str, str]] = {}            # lower-cased name or alias -> {"entity_id"} or {"entity_ref"}
        next_id = lambda: f"p-{len(proposals) + 1:03d}"

        for ent in extraction.get("entities", []):
            name = ent.get("canonical_name", "").strip()      # as integration stores it
            if not name:
                continue
            kind = ent.get("type", "unknown").lower()
            aliases = [a for a in ent.get("aliases", []) if a.strip().lower() != name.lower()]
            found = self._match(world_id, name, aliases, kind)
            pid = next_id()
            proposals.append({
                "id": pid, "kind": "entity", "change": "known" if found else "new",
                "summary": f"{'Known' if found else 'New'} {kind}: {found.canonical_name if found else name}",
                "confidence": CONFIDENCE, "match_entity_id": found.id if found else None,
                "proposed": {"canonical_name": name, "entity_type": kind, "aliases": aliases, "attributes": {}}})
            ref = {"entity_id": found.id} if found else {"entity_ref": pid}
            for n in [name, *aliases]:
                ref_of[n.lower()] = ref
            label = found.canonical_name if found else name
            if found:                                       # a known entity under a name it doesn't have yet
                stored = {found.canonical_name.lower(), *(a.alias.lower() for a in found.aliases)}
                for alias in dict.fromkeys(n for n in [name, *aliases] if n.lower() not in stored):
                    proposals.append({"id": next_id(), "kind": "alias", "change": "new",
                                      "summary": f"{label} is also called {alias}", "confidence": CONFIDENCE,
                                      "entity_id": found.id, "proposed": {"alias": alias}})

            for prop, value in (ent.get("attributes") or {}).items():
                if value in (None, ""):
                    continue
                current = None
                if found:
                    fact = self.db.query(Fact).filter(Fact.entity_id == found.id, Fact.property_name == prop).first()
                    active = self.world.fact_repo.get_active_version(fact.id) if fact else None
                    current = {"fact_version_id": active.id, "value": active.value} if active else None
                change = ("new" if current is None else
                          "known" if compare_fact_values(current["value"], value) else "changed")
                summary = (f"{label} {prop}: {current['value']} → {value}" if change == "changed"
                           else f"{label} {prop}: {value}")
                proposals.append({"id": next_id(), "kind": "fact", "change": change, "summary": summary,
                                  "confidence": CONFIDENCE, "entity": ref, "current": current,
                                  "proposed": {"property_name": prop, "value": value, "confidence": CONFIDENCE}})

        def resolve(name: str) -> Optional[Dict[str, str]]:
            """This chapter's entity, else a stored one (as integration resolves it)."""
            name = normalize_entity_name((name or "").strip())
            if name.lower() not in ref_of:
                found = self.world.find_entity(world_id, [name]) if name else None
                ref_of[name.lower()] = {"entity_id": found.id} if found else None
            return ref_of[name.lower()]

        seen = set()
        for rel in extraction.get("relationships", []):
            src, dst = resolve(rel.get("subject")), resolve(rel.get("object"))
            predicate = (rel.get("predicate") or "RELATED_TO").upper()
            if not src or not dst or src == dst or (key := (str(src), predicate, str(dst))) in seen:
                continue
            seen.add(key)
            current = self._current_relationship(world_id, src, dst, predicate)
            change = ("new" if current is None else
                      "known" if current["relationship_type"].upper() == predicate else "changed")
            subject, obj = rel["subject"], rel["object"]
            summary = (f"{subject} {current['relationship_type']} → {predicate} {obj}" if change == "changed"
                       else f"{subject} {predicate} {obj}")
            proposals.append({"id": next_id(), "kind": "relationship", "change": change, "summary": summary,
                              "confidence": CONFIDENCE, "source": src, "target": dst, "current": current,
                              "proposed": {"relationship_type": predicate, "chapter_id": chapter_id,
                                           "confidence": CONFIDENCE}})

        for ev in extraction.get("events", []):
            desc = (ev.get("evidence") or ev.get("description") or "").strip()
            if not desc:
                continue
            participants, taken = [], set()
            for p in ev.get("participants", []):
                p_name, role = (p, "PARTICIPANT") if isinstance(p, str) else (p["name"], p.get("role") or "PARTICIPANT")
                ref = resolve(p_name)
                if ref and str(ref) not in taken:
                    taken.add(str(ref))
                    participants.append({"entity": ref, "role": role})
            flat = " ".join(desc.split())                  # stored before line breaks were collapsed, or after
            known = next((e for e in self.db.query(Event).filter(Event.world_id == world_id,
                                                                 Event.chapter_id == chapter_id)
                          if " ".join(e.description.split()) == flat), None)
            proposals.append({"id": next_id(), "kind": "event", "change": "known" if known else "new",
                              "summary": f"{ev.get('type', 'EVENT').title()}: {desc[:120]}",
                              "confidence": CONFIDENCE, "participants": participants,
                              "proposed": {"description": desc, "event_type": ev.get("type", "EVENT"),
                                           "chapter_id": chapter_id}})

        return {"job_id": job_id, "world_id": world_id, "chapter_id": chapter_id, "chapter_number": chapter_number,
                "status": "ready", "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "proposals": proposals}

    def _current_relationship(self, world_id: str, src: Dict[str, str], dst: Dict[str, str],
                              predicate: str) -> Optional[Dict[str, str]]:
        if "entity_id" not in src or "entity_id" not in dst:
            return None                                     # an endpoint is a new entity: nothing stored yet
        pairs = [(src["entity_id"], dst["entity_id"])]
        if predicate in SYMMETRIC:
            pairs.append((dst["entity_id"], src["entity_id"]))
        for s, t in pairs:
            rel = self.db.query(Relationship).filter(Relationship.world_id == world_id,
                                                     Relationship.source_entity_id == s,
                                                     Relationship.target_entity_id == t).first()
            active = self.world.relationship_repo.get_active_version(rel.id) if rel else None
            if active:
                return {"relationship_id": rel.id, "relationship_version_id": active.id,
                        "relationship_type": active.relationship_type}
        return None

    def save(self, result: Dict[str, Any]) -> Path:
        path = proposals_path(result["job_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
