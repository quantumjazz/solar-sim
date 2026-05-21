"""Smoke test for the instructor-console Streamlit app.

Uses Streamlit's AppTest harness to run the app headlessly and exercise the
core flow: initial screen -> start a cohort -> run a period -> view reports.

Run from the repo root with:

    PYTHONPATH=sim-engine/src:app python3 -m pytest app/test_app.py
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_APP = str(Path(__file__).resolve().parent / "instructor_console.py")


def _start_two_team_cohort() -> AppTest:
    at = AppTest.from_file(_APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    at.text_area[0].set_value("Team A\nTeam B")
    start = next(b for b in at.button if "Start cohort" in b.label)
    start.click().run()
    assert not at.exception, at.exception
    return at


def test_initial_screen_renders():
    at = AppTest.from_file(_APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    titles = [t.value for t in at.title]
    assert any("Instructor Console" in t for t in titles)


def test_start_cohort_renders_workspace():
    at = _start_two_team_cohort()
    headers = [h.value for h in at.header]
    assert any("Period 1" in h for h in headers), headers


def test_run_period_produces_reports():
    at = _start_two_team_cohort()
    run_btn = next((b for b in at.button if b.label.startswith("Run period")), None)
    assert run_btn is not None, "Run-period button should be present"
    run_btn.click().run()
    assert not at.exception, at.exception
    # The workspace should advance to period 2 and show period-1 reports.
    headers = [h.value for h in at.header]
    assert any("Period 2" in h for h in headers), headers
    report_markers = [m.value for m in at.markdown if "Reports" in str(m.value)]
    assert any("period 1" in m for m in report_markers), report_markers
