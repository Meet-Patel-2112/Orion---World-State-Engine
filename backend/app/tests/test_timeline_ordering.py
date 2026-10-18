from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.chapter import Chapter
from app.models.event import Event, EventParticipant
from app.models.world import World
from app.models.entity import Entity
from app.services.timeline_service import TimelineService, event_sort_key


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()


def test_event_sort_key_no_chapter_first():
    """Events without a chapter sort before any event tagged with a chapter."""
    now = datetime(2026, 10, 1, 12, 0, 0)
    ev_no_ch = {"id": "1", "chapter_number": None, "sequence_index": None, "start_position": 100, "created_at": now}
    ev_ch1 = {"id": "2", "chapter_number": 1, "sequence_index": 0, "start_position": 10, "created_at": now}
    ev_ch2 = {"id": "3", "chapter_number": 2, "sequence_index": None, "start_position": None, "created_at": now}

    events = [ev_ch2, ev_ch1, ev_no_ch]
    sorted_evs = sorted(events, key=event_sort_key)
    assert [e["id"] for e in sorted_evs] == ["1", "2", "3"]


def test_event_sort_key_sequence_index_over_start_position():
    """Within a chapter, sequence_index takes precedence over start_position."""
    now = datetime(2026, 10, 1, 12, 0, 0)
    # ev_a has start_pos 100 but sequence_index 0 (author explicitly put it first)
    ev_a = {"id": "a", "chapter_number": 1, "sequence_index": 0, "start_position": 100, "created_at": now}
    # ev_b has start_pos 10 but sequence_index 1
    ev_b = {"id": "b", "chapter_number": 1, "sequence_index": 1, "start_position": 10, "created_at": now}
    # ev_c has sequence_index None -> sorts after non-null sequence_index
    ev_c = {"id": "c", "chapter_number": 1, "sequence_index": None, "start_position": 5, "created_at": now}

    events = [ev_c, ev_b, ev_a]
    sorted_evs = sorted(events, key=event_sort_key)
    assert [e["id"] for e in sorted_evs] == ["a", "b", "c"]


def test_event_sort_key_start_position_over_created_at():
    """When sequence_index is None, start_position determines order even if created later."""
    t1 = datetime(2026, 10, 1, 11, 40, 0)
    t2 = datetime(2026, 10, 1, 11, 41, 0)

    # ev_earlier_in_text created LATER (t2)
    ev_earlier_in_text = {"id": "vanish", "chapter_number": 2, "sequence_index": None, "start_position": 82, "created_at": t2}
    # ev_later_in_text created EARLIER (t1)
    ev_later_in_text = {"id": "confront", "chapter_number": 2, "sequence_index": None, "start_position": 146, "created_at": t1}

    events = [ev_later_in_text, ev_earlier_in_text]
    sorted_evs = sorted(events, key=event_sort_key)
    assert [e["id"] for e in sorted_evs] == ["vanish", "confront"]


def test_event_sort_key_created_at_fallback():
    """When both sequence_index and start_position are None, fall back to created_at."""
    t1 = datetime(2026, 10, 1, 10, 0, 0)
    t2 = datetime(2026, 10, 1, 11, 0, 0)

    ev_1 = {"id": "first", "chapter_number": 1, "sequence_index": None, "start_position": None, "created_at": t1}
    ev_2 = {"id": "second", "chapter_number": 1, "sequence_index": None, "start_position": None, "created_at": t2}

    events = [ev_2, ev_1]
    sorted_evs = sorted(events, key=event_sort_key)
    assert [e["id"] for e in sorted_evs] == ["first", "second"]


def test_timeline_service_get_world_timeline_ordering(db_session):
    """End-to-end integration test with database models."""
    world = World(id="w1", name="Test Realm")
    from app.models.manuscript import Manuscript
    ms = Manuscript(id="m1", world_id="w1", title="Manuscript")
    ch1 = Chapter(id="c1", manuscript_id="m1", chapter_number=1, title="Chapter One")
    ch2 = Chapter(id="c2", manuscript_id="m1", chapter_number=2, title="Chapter Two")
    db_session.add_all([world, ms, ch1, ch2])
    db_session.flush()

    base_time = datetime(2026, 10, 1, 10, 0, 0)

    # 1. Event with no chapter (e.g. world premise / backstory)
    ev_prologue = Event(
        id="ev-prologue",
        world_id="w1",
        chapter_id=None,
        description="The creation of the world",
        event_type="LORE",
        sequence_index=None,
        start_position=None,
        created_at=base_time + timedelta(hours=5)
    )

    # 2. Chapter 1: sequence_index=0
    ev_ch1_seq0 = Event(
        id="ev-ch1-seq0",
        world_id="w1",
        chapter_id="c1",
        description="Opening meeting",
        event_type="MEETING",
        sequence_index=0,
        start_position=200,
        created_at=base_time + timedelta(hours=1)
    )

    # 3. Chapter 1: sequence_index=1
    ev_ch1_seq1 = Event(
        id="ev-ch1-seq1",
        world_id="w1",
        chapter_id="c1",
        description="Second discussion",
        event_type="DISCUSSION",
        sequence_index=1,
        start_position=50,
        created_at=base_time + timedelta(hours=2)
    )

    # 4. Chapter 2: start_position=82 (created at t+4)
    ev_ch2_pos82 = Event(
        id="ev-ch2-pos82",
        world_id="w1",
        chapter_id="c2",
        description="Vanishing in night",
        event_type="DISAPPEARANCE",
        sequence_index=None,
        start_position=82,
        created_at=base_time + timedelta(hours=4)
    )

    # 5. Chapter 2: start_position=146 (created at t+3, earlier than t+4!)
    ev_ch2_pos146 = Event(
        id="ev-ch2-pos146",
        world_id="w1",
        chapter_id="c2",
        description="Confrontation next morning",
        event_type="CONFRONTATION",
        sequence_index=None,
        start_position=146,
        created_at=base_time + timedelta(hours=3)
    )

    db_session.add_all([ev_ch2_pos82, ev_ch1_seq1, ev_prologue, ev_ch2_pos146, ev_ch1_seq0])
    db_session.commit()

    service = TimelineService(db_session)
    response = service.get_world_timeline("w1")

    assert response.total == 5
    expected_order = [
        "ev-prologue",    # No chapter -> first
        "ev-ch1-seq0",    # Ch 1, sequence_index=0
        "ev-ch1-seq1",    # Ch 1, sequence_index=1
        "ev-ch2-pos82",   # Ch 2, start_pos 82 (even though created at t+4)
        "ev-ch2-pos146",  # Ch 2, start_pos 146 (created at t+3)
    ]
    actual_order = [e.id for e in response.events]
    assert actual_order == expected_order
