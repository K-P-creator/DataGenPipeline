import json
from pathlib import Path

DATA_DIR = Path("data")

total_loops = 0
positive_loops = 0

for file in DATA_DIR.glob("*_final_results*.json"):
    with open(file, "r") as f:
        data = json.load(f)

    for loop in data.get("loops", []):
        total_loops += 1

        baseline = loop["median_cycles"]["1"]

        # find best unroll factor
        best = min(
            v for k, v in loop["median_cycles"].items() if k != "1"
        )

        # check 2% improvement
        if best <= 0.98 * baseline:
            positive_loops += 1

print(f"Total loops: {total_loops}")
print(f"Positive loops (>=2% improvement): {positive_loops}")
print(f"Positive ratio: {positive_loops / total_loops:.3f}")
