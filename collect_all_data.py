#   Runs the data collection pipeline for all the available benchmarks in the
#   benchmarks config file. This will take a LONG time.
#
#   Make sure to follow the instructions in README before running this
#
#   Inputs: None
#   Outputs: Full dataset in the data file
#
#   Skips any benchmark that already has a completed output file in data/
#   whose filename starts with that benchmark's "name" field.

import json
from pathlib import Path

import per_benchmark


with open("configs/benchmarks.json", "r", encoding="utf-8") as f:
    benchmark_data = json.load(f)["benchmarks"]

data_dir = Path("data")
data_dir.mkdir(parents=True, exist_ok=True)

count = 0
skipped_count = 0

for i, benchmark in enumerate(benchmark_data):
    benchmark_name = benchmark["name"]

    # Check whether any file in data/ starts with the benchmark name
    already_completed = any(
        path.is_file() and path.name.startswith(benchmark_name)
        for path in data_dir.iterdir()
    )

    if already_completed:
        print(f"\nSkipping benchmark index {i} ({benchmark_name})")
        print(f"Found existing completed file in {data_dir}/ starting with '{benchmark_name}'")
        skipped_count += 1
        continue

    print(f"\nRunning benchmark index {i} ({benchmark_name})")
    count += per_benchmark.run_per_benchmark(i)
    print(f"\nCompleted benchmark index {i} ({benchmark_name})")
    print(f"Current dataset size: {count} samples\n")

print("Completed all benchmarks.")
print(f"Benchmarks skipped: {skipped_count}")
print(f"Final dataset size added this run: {count} samples!")