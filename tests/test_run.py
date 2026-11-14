"""The runner must finish every download before it builds any stack. Written with SI assistance (Claude Code)."""

import pipeline.run as runner
from pipeline.config import DSWX_LABEL_SITES, STACKS


def _record(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.nisar_fetch, "fetch_stack", lambda site, stack_id: calls.append(("fetch", site.name, stack_id)))
    monkeypatch.setattr(runner.dswx, "build_index", lambda site, stacks: calls.append(("index", site.name, sorted(stacks))) or [])
    monkeypatch.setattr(runner.dswx, "download", lambda site, index: calls.append(("labels", site.name)))
    monkeypatch.setattr(runner.stack, "build_stack", lambda site, stack_id: calls.append(("build", site.name, stack_id)) or "x.nc")
    monkeypatch.setattr(runner, "summarize", lambda path: "ok")
    return calls


def test_all_fetches_come_before_any_build(monkeypatch):
    calls = _record(monkeypatch)
    rows = runner.run()
    kinds = [c[0] for c in calls]
    last_fetch = max(i for i, k in enumerate(kinds) if k in ("fetch", "index", "labels"))
    first_build = min(i for i, k in enumerate(kinds) if k == "build")
    assert last_fetch < first_build
    n_stacks = sum(len(v) for v in STACKS.values())
    assert kinds.count("fetch") == kinds.count("build") == len(rows) == n_stacks
    assert [c[1] for c in calls if c[0] == "labels"] == list(DSWX_LABEL_SITES)
    # Water labels are asked only for that site's stacks.
    for c in calls:
        if c[0] == "index":
            assert c[2] == sorted(STACKS[c[1]])


def test_skip_fetch_only_builds(monkeypatch):
    calls = _record(monkeypatch)
    runner.run(skip_fetch=True)
    assert {c[0] for c in calls} == {"build"}
