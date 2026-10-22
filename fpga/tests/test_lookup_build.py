"""Verify lookup build selection using small bootstrap artifact fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from lookup_build import REVISION, select_build, sha, source_inputs, verify_base_report


class LookupBuildSelection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / "build/ypcb"
        self.build = self.base / "nextpnr-build"
        self.source = self.base / "nextpnr-himbaechel"
        self.database = self.build / "share/himbaechel/xilinx/chipdb-xc7k480t.bin"
        self.executable = self.build / "nextpnr-himbaechel"
        metadata = self.build / "himbaechel/CMakeFiles/nextpnr-himbaechel.dir"
        for path in (self.database, self.executable, self.source / "himbaechel/arch.cc",
                     metadata / "flags.make", metadata / "link.txt"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture native data\n")
        inputs = source_inputs(self.source)
        self.report = dict(status="PASS_TOOLCHAIN_BUILD_NOT_BOARD_SIGNOFF",
            pins={"nextpnr-himbaechel": ["https://example.invalid/source", REVISION]},
            source=str(self.source), build=str(self.build), inputs=inputs,
            native_source_inputs=sorted(inputs), commands=[dict(status="PASS", returncode=0)],
            artifacts={"nextpnr": dict(path=str(self.executable), sha256=sha(self.executable)),
                       "chipdb": dict(path=str(self.database), sha256=sha(self.database))})
        self.path = self.base / "bootstrap-1/report.json"
        self.path.parent.mkdir()
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report))

    def test_defaults_select_clean_bootstrap_outputs(self):
        build, source, database, report, executable, inputs = select_build(self.root, [])
        self.assertEqual((build, source, database, report, executable),
                         (self.build, self.source, self.database, self.path, self.executable))
        self.assertEqual(inputs[str(self.path)], sha(self.path))

    def test_explicit_paths_select_completed_build(self):
        selected = select_build(self.root, ["--build-dir", str(self.build), "--source", str(self.source),
            "--chipdb", str(self.database), "--build-report", str(self.path)])
        self.assertEqual(selected[4], self.executable)

    def test_missing_makefiles_metadata_has_actionable_error(self):
        (self.build / "himbaechel/CMakeFiles/nextpnr-himbaechel.dir/link.txt").unlink()
        with self.assertRaisesRegex(ValueError, "requires a completed Unix Makefiles build"):
            select_build(self.root, [])

    def test_changed_native_source_or_artifacts_rejected(self):
        for path in (self.source / "himbaechel/arch.cc", self.executable, self.database):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_text("changed\n")
                with self.assertRaises(ValueError):
                    select_build(self.root, [])
                path.write_bytes(original)

    def test_incomplete_or_unpinned_bootstrap_rejected(self):
        self.report["commands"][0]["status"] = "RUNNING"
        self.save()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            select_build(self.root, [])
        self.report["commands"][0]["status"] = "PASS"
        self.report["pins"]["nextpnr-himbaechel"][1] = "wrong"
        self.save()
        with self.assertRaisesRegex(ValueError, "source pin"):
            select_build(self.root, [])

    def test_new_native_source_file_rejected(self):
        (self.source / "new.cc").write_text("added later\n")
        with self.assertRaisesRegex(ValueError, "membership changed"):
            select_build(self.root, [])

    def test_explicit_legacy_manifest_is_supported(self):
        self.report = dict(status="PASS_NATIVE_EXECUTABLE_BUILD_AND_STARTUP",
            source_revision=REVISION, verification_inputs=source_inputs(self.source),
            executable=dict(path=str(self.executable), sha256=sha(self.executable)))
        self.save()
        executable, inputs = verify_base_report(self.path, self.build, self.source, self.database)
        self.assertEqual(executable, self.executable)
        self.assertEqual(inputs[str(self.path)], sha(self.path))


if __name__ == "__main__":
    unittest.main()
