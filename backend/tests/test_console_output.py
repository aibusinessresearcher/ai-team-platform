"""Offline regression coverage for Unicode console output and saved responses."""

import io
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from omegaconf import OmegaConf

from teamwork.backends import LLMBackend


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = ROOT / "interactive_experiments" / "run_experiment.py"
RESPONSE = (
    "Evidence: \u22121; caf\u00e9; \u6f22\u5b57; \U0001f642.\n"
    "MY RANKING:\n1. Candidate D\n2. Candidate C\n3. Candidate A\n4. Candidate B"
)
STRUCTURES = ("pooled", "sequential", "reciprocal_chain", "reciprocal_subgroups", "team")


class FixedBackend(LLMBackend):
    def invoke(self, *, agent_profile, trajectory):
        return RESPONSE


class OutputStream(io.TextIOWrapper):
    def __init__(self, buffer, encoding, terminal=False):
        super().__init__(buffer, encoding=encoding, errors="strict")
        self.terminal = terminal

    def isatty(self):
        return self.terminal


def run_offline_simulation(output_dir, structure):
    cfg = OmegaConf.create({"task": {
        "max_rounds": 2,
        "team_interdependence_type": structure,
        "input_prompt_file": str(ROOT / "interactive_experiments" / "prompts" / "student_body_president.json"),
        "seed": 42,
        "task_type": "ranking",
        "human_interaction": False,
        "backend": {"provider": "openai", "model": "offline-test"},
        "num_agents": 4,
        "small_groups": [[0, 1], [2, 3]],
        "small_group_reps": [1, 2],
        "small_group_rounds": 2,
    }})

    def configured_main(**kwargs):
        return lambda main: lambda: main(cfg)

    runtime = SimpleNamespace(runtime=SimpleNamespace(output_dir=str(output_dir)))
    random_state = random.getstate()
    try:
        with (
            patch.object(sys, "path", [str(ROOT), str(ENTRY_POINT.parent), *sys.path]),
            patch("hydra.main", side_effect=configured_main),
            patch("hydra.core.hydra_config.HydraConfig.get", return_value=runtime),
            patch("dotenv.load_dotenv", return_value=False),
            patch("teamwork.backend_utils.get_api_key", return_value="offline-not-a-real-key"),
            patch("teamwork.backend_utils.create_backend_from_config", side_effect=lambda **kwargs: FixedBackend()),
            patch("socket.socket.connect", side_effect=AssertionError("Network calls are forbidden in this test")),
        ):
            runpy.run_path(str(ENTRY_POINT), run_name="__main__")
    finally:
        random.setstate(random_state)


class ConsoleOutputTests(unittest.TestCase):
    def assert_saved_response(self, output_dir, structure):
        conversation = json.loads((Path(output_dir) / "conversation.json").read_text(encoding="utf-8"))
        for agent_id in range(4):
            own_turns = [turn for turn in conversation[f"agent_{agent_id}"] if turn["speaker_id"] == agent_id]
            self.assertTrue(own_turns)
            for turn in own_turns:
                self.assertEqual(turn["content"], RESPONSE)
        results = json.loads((Path(output_dir) / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(results), 4 if structure == "pooled" else 2)
        for result in results.values():
            self.assertEqual(result["score"], 0.0)
            self.assertEqual(result["answer"], {"Candidate D": 1, "Candidate C": 2, "Candidate A": 3, "Candidate B": 4})

    def test_strict_windows_encoding_reproduces_failure(self):
        with OutputStream(io.BytesIO(), "cp1252") as output:
            with self.assertRaises(UnicodeEncodeError):
                print(RESPONSE, file=output)

    def test_all_protocols_complete_without_changing_saved_unicode(self):
        for encoding in ("cp1252", "ascii", "utf-8"):
            for terminal in (False, True):
                for structure in STRUCTURES:
                    with self.subTest(encoding=encoding, terminal=terminal, structure=structure):
                        stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
                        with (
                            OutputStream(stdout_bytes, encoding, terminal) as stdout,
                            OutputStream(stderr_bytes, encoding, terminal) as stderr,
                            tempfile.TemporaryDirectory() as output_dir,
                        ):
                            with redirect_stdout(stdout), redirect_stderr(stderr):
                                run_offline_simulation(output_dir, structure)
                                print(RESPONSE, file=sys.stderr)
                            stdout.flush()
                            stderr.flush()
                            self.assertEqual(stdout.encoding, encoding)
                            self.assertEqual(stderr.encoding, encoding)
                            expected_display = RESPONSE.encode(encoding, errors="backslashreplace")
                            self.assertIn(expected_display, stdout_bytes.getvalue().replace(b"\r\n", b"\n"))
                            self.assertIn(expected_display, stderr_bytes.getvalue().replace(b"\r\n", b"\n"))
                            self.assert_saved_response(output_dir, structure)

    def test_unicode_capture_streams_without_reconfigure(self):
        with tempfile.TemporaryDirectory() as output_dir:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                run_offline_simulation(output_dir, "team")
            self.assertIn(RESPONSE, stdout.getvalue())
            self.assert_saved_response(output_dir, "team")

    def test_redirected_subprocess_with_strict_windows_encoding(self):
        environment = dict(os.environ)
        environment.update({
            "PYTHONUTF8": "0",
            "PYTHONIOENCODING": "cp1252:strict",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT),
        })
        for name in tuple(environment):
            if name.endswith("_API_KEY"):
                environment.pop(name)
        driver = (
            "import runpy, sys; "
            "test = runpy.run_path(sys.argv[1]); "
            "test['run_offline_simulation'](sys.argv[2], 'reciprocal_subgroups'); "
            "print(test['RESPONSE'], file=sys.stderr)"
        )
        with tempfile.TemporaryDirectory() as output_dir:
            completed = subprocess.run(
                [sys.executable, "-B", "-c", driver, str(Path(__file__).resolve()), output_dir],
                cwd=ROOT, env=environment, capture_output=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode("ascii", errors="backslashreplace"))
            expected_display = RESPONSE.encode("cp1252", errors="backslashreplace")
            self.assertIn(expected_display, completed.stdout.replace(b"\r\n", b"\n"))
            self.assertIn(expected_display, completed.stderr.replace(b"\r\n", b"\n"))
            self.assert_saved_response(output_dir, "reciprocal_subgroups")


if __name__ == "__main__":
    unittest.main()
