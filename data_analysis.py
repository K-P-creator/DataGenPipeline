import json
import hashlib
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path("data")

total_loops = 0
positive_loops = 0

# hash -> list of occurrences
duplicate_map = defaultdict(list)


def make_exact_loop_signature(loop: dict) -> tuple:
    """
    Exact duplicate = same physical loop in source code.

    We ONLY use:
    - loop_location
    - loop_range

    This allows detection across different benchmarks if they refer
    to the same underlying source file/line.
    """
    features = loop.get("features", {})

    loop_location = features.get("loop_location", "UNKNOWN")
    loop_range = features.get("loop_range", "UNKNOWN")

    return (
        ("loop_location", loop_location),
        ("loop_range", loop_range),
    )


def hash_signature(signature: tuple) -> str:
    raw = json.dumps(signature, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


for file in DATA_DIR.glob("*_final_results*.json"):
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    benchmark_name = file.stem.replace("_final_results", "")

    for loop in data.get("loops", []):
        total_loops += 1

        baseline = loop["median_cycles"]["1"]

        # find best unroll factor
        best = min(
            v for k, v in loop["median_cycles"].items() if k != "1"
        )

        # check 2% improvement
        is_positive = best <= 0.98 * baseline
        if is_positive:
            positive_loops += 1

        signature = make_exact_loop_signature(loop)
        loop_hash = hash_signature(signature)

        duplicate_map[loop_hash].append({
            "benchmark": benchmark_name,
            "file": str(file),
            "loop_index": loop.get("loop_index"),
            "loop_location": loop.get("features", {}).get("loop_location", "UNKNOWN"),
            "loop_range": loop.get("features", {}).get("loop_range", "UNKNOWN"),
            "baseline_cycles": baseline,
            "best_cycles": best,
            "positive": is_positive,
        })

unique_hashes = len(duplicate_map)
duplicate_groups = {h: entries for h, entries in duplicate_map.items() if len(entries) > 1}
duplicate_group_count = len(duplicate_groups)
duplicate_loop_count = sum(len(entries) for entries in duplicate_groups.values())

print(f"Total loops: {total_loops}")
print(f"Positive loops (>=2% improvement): {positive_loops}")
print(f"Positive ratio: {positive_loops / total_loops:.3f}")

print(f"\nUnique exact loop hashes: {unique_hashes}")
print(f"Exact duplicate groups: {duplicate_group_count}")
print(f"Loops involved in exact duplicates: {duplicate_loop_count}")
print(f"Exact duplicate ratio: {duplicate_loop_count / total_loops:.3f}")

"""
if duplicate_groups:
    print("\nExact duplicate groups found:\n")
    for i, (loop_hash, entries) in enumerate(sorted(duplicate_groups.items()), start=1):
        print(f"Group {i}")
        print(f"Hash: {loop_hash}")
        print(f"Count: {len(entries)}")
        for entry in entries:
            print(
                f"  - loop_index={entry['loop_index']}, "
                f"location={entry['loop_location']}, "
                f"range={entry['loop_range']}, "
                f"benchmark={entry['benchmark']}, "
                f"positive={entry['positive']}"
            )
        print()
else:
    print("\nNo exact duplicate groups found.")
"""