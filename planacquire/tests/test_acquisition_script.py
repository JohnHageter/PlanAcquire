"""Tests for Module/acquisition/script_engine.py."""
from __future__ import annotations

import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from planacquire.script_engine import (
    ScriptContext,
    ScriptEngine,
    ScriptSyntaxError,
    parse,
)



def _run(script: str, **ctx_kwargs):
    """Parse + execute *script* with _do_delay patched to a no-op."""
    engine = ScriptEngine()
    engine.load(script)
    ctx = ScriptContext(**ctx_kwargs)
    with patch.object(engine, "_do_delay"):
        engine.run(ctx)
    return engine, ctx


def _mock_camera():
    cam = MagicMock()
    cam.software_fps = 25.0
    return cam



class TestParser(unittest.TestCase):

    def test_set_parsed(self):
        _, cmds = parse("SET exposure = 8000")
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].kind, "SET")
        self.assertEqual(cmds[0].args, ["exposure", "8000"])

    def test_record_parsed(self):
        _, cmds = parse("RECORD 60")
        self.assertEqual(cmds[0].kind, "RECORD")
        self.assertEqual(cmds[0].args, ["60"])

    def test_delay_parsed(self):
        _, cmds = parse("DELAY 3.5")
        self.assertEqual(cmds[0].kind, "DELAY")
        self.assertEqual(cmds[0].args, ["3.5"])

    def test_daq_pulse_parsed(self):
        _, cmds = parse("DAQ_PULSE Dev1/port0/line0, 1.0")
        self.assertEqual(cmds[0].kind, "DAQ_PULSE")
        self.assertEqual(cmds[0].args[1], "1.0")

    def test_comments_stripped(self):
        _, cmds = parse("# full-line comment\nSET gain = 2  # inline")
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].args, ["gain", "2"])

    def test_unknown_command_raises(self):
        with self.assertRaises(ScriptSyntaxError):
            parse("FROBNICIATE 42")

    def test_repeat_missing_end_raises(self):
        with self.assertRaises(ScriptSyntaxError):
            parse("REPEAT 3:\n  LOG \"hi\"")

    def test_repeat_block_parsed(self):
        _, cmds = parse("REPEAT 5:\n  LOG \"tick\"\nEND")
        self.assertEqual(cmds[0].kind, "REPEAT")
        self.assertEqual(cmds[0].args[0], "5")
        self.assertEqual(len(cmds[0].body), 1)



class TestSetCommand(unittest.TestCase):

    def test_set_exposure_calls_camera(self):
        cam = _mock_camera()
        _run("SET exposure = 8000", camera_worker=cam)
        cam.set_parameter.assert_called_once_with("exposure", 8000.0)

    def test_set_fps_calls_camera(self):
        cam = _mock_camera()
        _run("SET fps = 30", camera_worker=cam)
        cam.set_parameter.assert_called_once_with("fps", 30.0)

    def test_set_output_updates_context(self):
        _, ctx = _run("SET output = /data/exp1")
        self.assertEqual(ctx.output_dir, "/data/exp1")

    def test_set_subject_updates_context(self):
        _, ctx = _run("SET subject = fish01")
        self.assertEqual(ctx.subject, "fish01")

    def test_set_unknown_key_silently_ignored(self):
        """An unknown SET key must not raise."""
        _run("SET nonexistent_key = 99")



class TestRecordCommand(unittest.TestCase):

    def test_record_calls_start_and_stop(self):
        cam = _mock_camera()
        with tempfile.TemporaryDirectory() as tmp:
            _run("RECORD 60", camera_worker=cam, output_dir=tmp)
        cam.start_recording.assert_called_once()
        cam.stop_recording.assert_called_once()

    def test_record_without_camera_does_not_raise(self):
        engine = ScriptEngine()
        engine.load("RECORD 10")
        ctx = ScriptContext()
        with patch.object(engine, "_do_delay"):
            engine.run(ctx)

    def test_record_increments_video_counter(self):
        cam = _mock_camera()
        with tempfile.TemporaryDirectory() as tmp:
            _, ctx = _run("RECORD 5\nRECORD 5", camera_worker=cam, output_dir=tmp)
        self.assertEqual(ctx.video_counter, 2)

    def test_record_skip_recording_flag(self):
        """With skip_recording=True, start_recording must not be called."""
        cam = _mock_camera()
        engine = ScriptEngine()
        engine.load("RECORD 10")
        ctx = ScriptContext(camera_worker=cam, skip_recording=True)
        with patch.object(engine, "_do_delay"):
            engine.run(ctx)
        cam.start_recording.assert_not_called()


# ── DELAY command ─────────────────────────────────────────────────────────────

class TestDelayCommand(unittest.TestCase):

    def test_delay_dispatches_correct_duration(self):
        """The engine calls _do_delay(3.0) for 'DELAY 3'."""
        engine = ScriptEngine()
        engine.load("DELAY 3")
        with patch.object(engine, "_do_delay") as mock_delay:
            engine.run(ScriptContext())
        mock_delay.assert_called_once_with(3.0)

    def test_delay_can_be_aborted(self):
        """abort() during a long DELAY must return quickly without hanging."""
        engine = ScriptEngine()
        engine.load("DELAY 999")
        ctx = ScriptContext()
        killer = threading.Timer(0.05, engine.abort)
        killer.start()
        engine.run(ctx)   # must return; test runner provides the timeout
        killer.cancel()


# ── LOG command ───────────────────────────────────────────────────────────────

class TestLogCommand(unittest.TestCase):

    def test_log_calls_callback(self):
        messages = []
        _run('LOG "hello world"', log_callback=messages.append)
        self.assertTrue(any("hello world" in m for m in messages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
