"""Validate frame files against the exact target part's address space."""
import json


def check_frames(frame_path, part_json, require_nonzero=True):
    part = json.loads(part_json.read_text())
    allowed = set()
    buses = {"CLB_IO_CLK": 0, "BLOCK_RAM": 1, "CFG_CLB": 2}
    for half, region in part["global_clock_regions"].items():
        for row, config_row in region["rows"].items():
            for kind, bus in config_row["configuration_buses"].items():
                for column, config_column in bus["configuration_columns"].items():
                    base = (buses[kind] << 23) | ((half == "bottom") << 22) | (int(row) << 17) | (int(column) << 7)
                    allowed.update(base + minor for minor in range(config_column["frame_count"]))
    seen = set()
    nonzero = 0
    with frame_path.open() as stream:
        for number, line in enumerate(stream, 1):
            fields = line.split()
            if len(fields) != 2:
                raise ValueError(f"Malformed frame line {number}")
            address = int(fields[0], 16)
            words = [int(word, 16) for word in fields[1].split(",")]
            if address not in allowed or address in seen:
                raise ValueError(f"Invalid/duplicate target frame address on line {number}: {address:#x}")
            if len(words) != 101 or any(word < 0 or word > 0xffffffff for word in words):
                raise ValueError(f"Invalid 101-word frame data on line {number}")
            nonzero += sum(word != 0 for word in words)
            seen.add(address)
    if not seen or (require_nonzero and not nonzero):
        raise ValueError("Empty configuration data")
    return dict(supplied_frames=len(seen), legal_target_frames=len(allowed), nonzero_words=nonzero,
                missing_frames_zero_filled_by_assembler=len(allowed - seen))
