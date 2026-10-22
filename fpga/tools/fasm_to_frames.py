#!/usr/bin/env python3
"""Run the pinned converter while reusing its read-only per-device Grid."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "build/ypcb/prjxray/utils/fasm2frames.py"


def main():
    spec = importlib.util.spec_from_file_location("tiny_gpu_vendor_fasm2frames", SOURCE)
    converter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(converter)

    class CachedDatabase(converter.Database):
        calls = 0
        constructions = 0

        def grid(self):
            type(self).calls += 1
            if not hasattr(self, "_tiny_gpu_grid"):
                self._tiny_gpu_grid = super().grid()
                type(self).constructions += 1
            return self._tiny_gpu_grid

    # The converter reads Grid's geometry/bit records; its bank aliases and
    # accumulated configuration bits live in separate dictionaries. The vendor
    # source and all conversion rules remain unchanged.
    converter.Database = CachedDatabase
    try:
        converter.main()
    finally:
        print(f"TINYGPU_GRID_CACHE calls={CachedDatabase.calls} constructions={CachedDatabase.constructions}",
              file=sys.stderr)


if __name__ == "__main__": main()
