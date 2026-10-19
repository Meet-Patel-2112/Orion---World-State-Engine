import json

import extractor.__main__ as cli
from extractor.pipeline import LISTS


def test_predict_v2_writes_one_prediction_per_chapter_in_the_scorer_layout(tmp_path, monkeypatch):
    gold = tmp_path / "gold" / "some_work"
    gold.mkdir(parents=True)
    for n in (1, 3):
        (gold / f"ch{n:02d}.json").write_text(json.dumps({"doc_id": f"some_work/ch{n:02d}", "text": f"Text {n}."}),
                                              encoding="utf-8")
    calls = []
    monkeypatch.setattr(cli, "extract", lambda story_id, text: calls.append((story_id, text)) or
                        {"story_id": story_id, "text": text, **{k: [] for k in LISTS}})
    assert cli.main(["predict-v2", str(tmp_path / "gold" / "some_work" / "ch03.json"), str(tmp_path / "gold"),
                     "--out-dir", str(tmp_path / "pred")]) == 0
    assert calls == [("some_work/ch03", "Text 3."), ("some_work/ch01", "Text 1."), ("some_work/ch03", "Text 3.")]
    doc = json.loads((tmp_path / "pred" / "some_work" / "ch01.json").read_text(encoding="utf-8"))
    assert doc["doc_id"] == "some_work/ch01" and doc["text"] == "Text 1."
