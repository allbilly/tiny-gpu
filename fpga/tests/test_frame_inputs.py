"""Reject stale conversion evidence without running the native frame tools."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_frame_tools
from frame_inputs import capture_frame_inputs, sha, verify_frame_inputs


class FrameDependencies(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / "build/ypcb"
        self.db = self.base / "prjxray-db/kintex7"
        paths = [self.root / "fpga/tools" / name for name in (
            "frame_inputs.py", "check_frame_tools.py", "fasm_to_frames.py",
            "frame_check.py", "board.py", "stage_run.py")]
        paths += [self.base / name for name in (
            "prjxray-build/tools/xc7frames2bit", "xray-venv/bin/python", "xray-venv/pyvenv.cfg",
            "prjxray/utils/fasm2frames.py", "prjxray/prjxray/db.py",
            "prjxray/third_party/fasm/fasm/parser.py", "xray-venv/lib/python3.13/site-packages/textx/__init__.py")]
        self.grid = self.db / "xc7k480t/tilegrid.json"
        self.segbits = self.db / "segbits_clbll_l.db"
        paths += [self.grid, self.segbits]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original\n")
        self.inputs = capture_frame_inputs(self.root, self.base)
        self.record = dict(inputs=self.inputs, frame_tool_inputs=sorted(self.inputs))

    def reports(self):
        paths = []
        for cached in (False, True):
            out = self.base / str(cached)
            out.mkdir()
            frames = out / "empty-design.frames"
            frames.write_text("same frames\n")
            report = dict(self.record, status="PASS_EXACT_PART_FRAME_TOOLS_ONLY",
                part=check_frame_tools.PART, grid_cache=cached,
                artifacts={frames.name: sha(frames)}, frame_validation={}, commands=[])
            path = out / "report.json"
            path.write_text(json.dumps(report))
            paths.append(path)
        return paths

    def compare(self, paths):
        with patch.multiple(check_frame_tools, ROOT=self.root, BASE=self.base, DB=self.db), contextlib.redirect_stdout(io.StringIO()):
            check_frame_tools.compare_reports(paths)

    def test_comparison_propagates_all_bound_dependencies_and_evidence(self):
        reports = self.reports()
        self.compare(reports)
        result = json.loads((self.base / "frame-grid-cache-check.json").read_text())
        self.assertEqual(result["frame_tool_inputs"], sorted(self.inputs))
        for path, digest in self.inputs.items():
            self.assertEqual(result["inputs"][path], digest)
        for report in reports:
            self.assertEqual(result["inputs"][str(report)], sha(report))
            frame = report.parent / "empty-design.frames"
            self.assertEqual(result["inputs"][str(frame)], sha(frame))

    def test_changed_tilegrid_cannot_be_rebound_at_comparison(self):
        reports = self.reports()
        self.grid.write_text("changed after both checks\n")
        with self.assertRaisesRegex(ValueError, "dependency changed"):
            self.compare(reports)

    def test_database_features_and_installed_parser_are_bound(self):
        paths = [self.segbits, self.base / "xray-venv/lib/python3.13/site-packages/textx/__init__.py"]
        for path in paths:
            with self.subTest(path=path):
                path.write_text("changed\n")
                with self.assertRaisesRegex(ValueError, "dependency changed"):
                    verify_frame_inputs(self.record, self.root, self.base)
                path.write_text("original\n")

    def test_new_optional_database_file_is_rejected(self):
        (self.db / "required_features.fasm").write_text("new feature\n")
        with self.assertRaisesRegex(ValueError, "dependency set"):
            verify_frame_inputs(self.record, self.root, self.base)

    def test_legacy_incomplete_reports_are_rejected(self):
        reports = self.reports()
        for path in reports:
            report = json.loads(path.read_text())
            report.pop("frame_tool_inputs")
            path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "dependency set"):
            self.compare(reports)


if __name__ == "__main__":
    unittest.main()
