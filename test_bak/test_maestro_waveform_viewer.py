from __future__ import annotations

import pytest

from virtuoso_bridge.virtuoso.maestro import (
    close_waveform_viewer,
    maestro_close_waveform_viewer_skill,
    maestro_open_waveform_viewer_skill,
    open_waveform_viewer,
)


def test_maestro_open_waveform_viewer_skill_plots_explicit_signals() -> None:
    skill = maestro_open_waveform_viewer_skill(
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["/IN", "/OUT"],
        results_dir="/tmp/psf/tran/psf",
        result="tran",
    )

    assert "isCallable('awvCreatePlotWindow)" in skill
    assert 'maeOpenSetup("demoLib" "tb_inv" "maestro" ?application "Assembler" ?mode "r")' in skill
    assert 'maeOpenResults(?session vbSession ?history "Interactive.1")' in skill
    assert 'openResults("/tmp/psf/tran/psf")' in skill
    assert 'v("/IN" ?result "tran" ?resultsDir vbResultsDir)' in skill
    assert 'v("/OUT" ?result "tran" ?resultsDir vbResultsDir)' in skill
    assert "awvCreatePlotWindow()" in skill
    assert 'awvPlotWaveform(vbWindowId vbWaveforms ?expr list("/IN" "/OUT"))' in skill


def test_maestro_open_waveform_viewer_keeps_results_session_alive_on_success() -> None:
    skill = maestro_open_waveform_viewer_skill(
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["/OUT"],
        results_dir="/tmp/psf/tran/psf",
    )

    assert "vbOpenOk = t" in skill
    assert 'list("opened" "demoLib" "tb_inv" "maestro" "Interactive.1" vbSession vbWindowId)' in skill
    assert "unless(vbOpenOk" in skill


def test_maestro_open_waveform_viewer_cleans_up_failed_open() -> None:
    skill = maestro_open_waveform_viewer_skill(
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["/OUT"],
        results_dir="/tmp/psf/tran/psf",
    )

    assert "vbOpenResult = errset(progn(" in skill
    assert "unless(vbOpenOk" in skill
    assert "hiCloseWindow(vbWindowId)" in skill
    assert "maeCloseSession(?session vbSession ?forceClose t)" in skill
    assert 'error("open waveform viewer failed")' in skill


def test_maestro_open_waveform_viewer_escapes_string_inputs() -> None:
    skill = maestro_open_waveform_viewer_skill(
        'demo"Lib\\1',
        'tb"inv\\2',
        'Interactive."3\\4',
        signals=['/A"NET\\1'],
        test='tr"an\\5',
        result='res"ult\\6',
        results_dir='/tmp/a"b\\c',
    )

    assert 'demo\\"Lib\\\\1' in skill
    assert 'tb\\"inv\\\\2' in skill
    assert 'Interactive.\\"3\\\\4' in skill
    assert '/A\\"NET\\\\1' in skill
    assert 'tr\\"an\\\\5' in skill
    assert 'res\\"ult\\\\6' in skill
    assert '/tmp/a\\"b\\\\c' in skill


def test_maestro_open_waveform_viewer_requires_explicit_results_dir_to_open() -> None:
    skill = maestro_open_waveform_viewer_skill(
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["/OUT"],
        results_dir="/tmp/psf/tran/psf",
    )

    assert 'when(vbResultsDir && !vbRawResultsOpen error("open raw results failed"))' in skill


def test_maestro_open_waveform_viewer_docstring_documents_test_and_result() -> None:
    doc = maestro_open_waveform_viewer_skill.__doc__ or ""

    assert "test: Maestro test name" in doc
    assert "result: Spectre result name" in doc


def test_maestro_open_waveform_viewer_skill_can_fallback_to_maestro_outputs() -> None:
    skill = maestro_open_waveform_viewer_skill(
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["vout"],
        test="tran_test",
    )

    assert 'maeGetOutputValue("vout" "tran_test")' in skill
    assert 'list("opened" "demoLib" "tb_inv" "maestro" "Interactive.1" vbSession vbWindowId)' in skill


def test_maestro_open_waveform_viewer_requires_signals() -> None:
    with pytest.raises(ValueError, match="signals must not be empty"):
        maestro_open_waveform_viewer_skill("demoLib", "tb_inv", "Interactive.1", signals=[])


def test_maestro_close_waveform_viewer_skill_closes_window_and_session() -> None:
    skill = maestro_close_waveform_viewer_skill(window="window:7", session="fnxSession2")

    assert "vbWindow = window(7)" in skill
    assert 'vbSession = "fnxSession2"' in skill
    assert "hiCloseWindow(vbWindow)" in skill
    assert "maeCloseSession(?session vbSession ?forceClose t)" in skill
    assert "maeGetSessions()" in skill
    assert "member(vbSession" in skill
    assert 'error("close waveform session failed")' in skill


def test_maestro_close_waveform_viewer_escapes_session() -> None:
    skill = maestro_close_waveform_viewer_skill(session='fnx"Session\\2')

    assert 'vbSession = "fnx\\"Session\\\\2"' in skill


def test_maestro_close_waveform_viewer_accepts_window_object_text() -> None:
    skill = maestro_close_waveform_viewer_skill(window="window(8)")

    assert "vbWindow = window(8)" in skill
    assert "vbSession = nil" in skill


def test_maestro_close_waveform_viewer_requires_target() -> None:
    with pytest.raises(ValueError, match="window or session must be provided"):
        maestro_close_waveform_viewer_skill()


def test_maestro_close_waveform_viewer_rejects_blank_session() -> None:
    with pytest.raises(ValueError, match="session must not be blank"):
        maestro_close_waveform_viewer_skill(session="  ")


def test_maestro_close_waveform_viewer_rejects_unsafe_window_ref() -> None:
    with pytest.raises(ValueError, match="window must be a window number"):
        maestro_close_waveform_viewer_skill(window='window(7) hiCloseWindow(window(1))')


def test_maestro_close_waveform_viewer_rejects_invalid_window_number() -> None:
    with pytest.raises(ValueError, match="positive window number"):
        maestro_close_waveform_viewer_skill(window=0)


def test_open_waveform_viewer_executes_generated_skill() -> None:
    class Client:
        skill: str | None = None
        timeout: int | None = None

        def execute_skill(self, skill: str, *, timeout: int):
            self.skill = skill
            self.timeout = timeout
            return {"status": "success", "output": '("opened" "demoLib" "tb_inv")'}

    client = Client()
    result = open_waveform_viewer(
        client,
        "demoLib",
        "tb_inv",
        "Interactive.1",
        signals=["/OUT"],
        timeout=30,
    )

    assert result == {"status": "success", "output": '("opened" "demoLib" "tb_inv")'}
    assert client.timeout == 30
    assert client.skill is not None
    assert 'awvPlotWaveform(vbWindowId vbWaveforms ?expr list("/OUT"))' in client.skill


def test_open_waveform_viewer_docstring_documents_raw_result_contract() -> None:
    doc = open_waveform_viewer.__doc__ or ""

    assert "raw VirtuosoResult" in doc
    assert "output" in doc
    assert "session" in doc
    assert "window" in doc


def test_close_waveform_viewer_executes_generated_skill() -> None:
    class Client:
        skill: str | None = None
        timeout: int | None = None

        def execute_skill(self, skill: str, *, timeout: int):
            self.skill = skill
            self.timeout = timeout
            return {"status": "success", "output": '("closed" "fnxSession2" window:7)'}

    client = Client()
    result = close_waveform_viewer(
        client,
        window=7,
        session="fnxSession2",
        timeout=10,
    )

    assert result == {"status": "success", "output": '("closed" "fnxSession2" window:7)'}
    assert client.timeout == 10
    assert client.skill is not None
    assert "vbWindow = window(7)" in client.skill
    assert 'vbSession = "fnxSession2"' in client.skill
