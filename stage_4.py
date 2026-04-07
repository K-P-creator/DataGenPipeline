#   ### Stage 4
#   Runs the timed pass with unroll factor set to 1. This will run 
#   `warmup_runs + timed_runs` number of times, and saves each time, 
#   including the median time. This median time will serve as a baseline 
#   for all the loops.

# Create the executable for stage 4
#   Example of what this stage will do (using atax benchmark as an example):
#   ```
#       temp$ ../../llvm-LUFG/build/bin/opt -strip-debug atax.ll -S -o atax-stripped.ll --my-unroll-factor=0 --my-hot-loop-index=0
#       temp$ ../../llvm-LUFG/build/bin/llc atax-stripped.ll -filetype=obj -o atax.o
#       temp$ clang -no-pie atax.o ../polybench-c-3.2/utilities/polybench.c -o atax.out
#       temp$ ./atax.out
#       TIMER_NS: 12345678
#   ```

# Generate the object file with llc

# Generate the executable and link with any neccesary files with clang ("files_to_link" in the benchmark JSON)

# Run and capture timer output, parse, and save median time to the JSON from stage 3, making sure to ignore the warmup runs.
# This will be the baseline runtime ("median_times_ns"["1"]) for the loops in this benchmark.

from pathlib import Path
from statistics import median


def run_stage4_run_timed_pass(
    data_mode_opt_pass_filename: str,
    llvm_IR_filename: str,
    benchmark_json_index: int,
) -> int:
    import json
    import subprocess

    stage3_json_path = Path(data_mode_opt_pass_filename)
    llvm_ir_path = Path(llvm_IR_filename)

    if not stage3_json_path.exists():
        raise FileNotFoundError(
            f"Stage 4 failed: Stage 3 JSON file not found: {stage3_json_path}"
        )

    if not llvm_ir_path.exists():
        raise FileNotFoundError(
            f"Stage 4 failed: LLVM IR file not found: {llvm_ir_path}"
        )

    # -------------------------------------------------------------------------
    # Load configs
    # -------------------------------------------------------------------------
    with open("configs/benchmarks.json", "r", encoding="utf-8") as f:
        benchmarks = json.load(f)["benchmarks"]

    benchmark_info = benchmarks[benchmark_json_index]

    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    llc_path = global_cfg["llc_path"]
    warmup_runs = int(global_cfg["warmup_runs"])
    timed_runs = int(global_cfg["timed_runs"])

    work_dir = Path(benchmark_info["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    files_to_link = benchmark_info.get("files_to_link", [])
    run_args = benchmark_info.get("run_args", [])

    # -------------------------------------------------------------------------
    # Generate filenames
    # -------------------------------------------------------------------------
    object_path = llvm_ir_path.with_suffix(".o")
    exe_path = llvm_ir_path.with_suffix(".out")

    # -------------------------------------------------------------------------
    # Generate the object file with llc (NO STRIP STEP)
    # -------------------------------------------------------------------------
    llc_cmd = [
        llc_path,
        str(llvm_ir_path),
        "-filetype=obj",
        "-o",
        str(object_path),
    ]

    llc_result = subprocess.run(
        llc_cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if llc_result.returncode != 0:
        raise RuntimeError(
            "Stage 4 failed during llc object generation.\n"
            f"Command: {' '.join(llc_cmd)}\n"
            f"STDOUT:\n{llc_result.stdout}\n"
            f"STDERR:\n{llc_result.stderr}"
        )

    # -------------------------------------------------------------------------
    # Generate executable with clang
    # -------------------------------------------------------------------------
    clang_cmd = ["clang", "-no-pie", str(object_path)]

    source_dir = Path(benchmark_info["source_dir"])
    for file_to_link in files_to_link:
        clang_cmd.append(str(source_dir / file_to_link))

    clang_cmd.extend(["-o", str(exe_path)])

    clang_result = subprocess.run(
        clang_cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if clang_result.returncode != 0:
        raise RuntimeError(
            "Stage 4 failed during executable link.\n"
            f"Command: {' '.join(clang_cmd)}\n"
            f"STDOUT:\n{clang_result.stdout}\n"
            f"STDERR:\n{clang_result.stderr}"
        )

    # -------------------------------------------------------------------------
    # Run executable and collect timing
    # -------------------------------------------------------------------------
    total_runs = warmup_runs + timed_runs
    all_times_ns = []

    for i in range(total_runs):
        run_cmd = [str(exe_path), *run_args]

        result = subprocess.run(
            run_cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Stage 4 execution failed on run {i}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        timer_val = None
        for line in result.stdout.splitlines():
            if line.startswith("TIMER_NS:"):
                timer_val = int(line.split(":")[1].strip())

        if timer_val is None:
            raise RuntimeError(f"No TIMER_NS output found on run {i}")

        all_times_ns.append(timer_val)

    timed_only = all_times_ns[warmup_runs:]
    baseline_runtime = int(median(timed_only))

    # -------------------------------------------------------------------------
    # Update Stage 3 JSON
    # -------------------------------------------------------------------------
    with open(stage3_json_path, "r", encoding="utf-8") as f:
        stage3_data = json.load(f)

    for loop in stage3_data.get("loops", []):
        loop.setdefault("median_times_ns", {})
        loop["median_times_ns"]["1"] = baseline_runtime

    stage3_data["stage_4"] = {
        "baseline_runtime_ns": baseline_runtime,
        "all_times_ns": all_times_ns,
    }

    with open(stage3_json_path, "w", encoding="utf-8") as f:
        json.dump(stage3_data, f, indent=2)

    print(f"Stage 4 complete. Baseline runtime: {baseline_runtime} ns")

    if __name__ == "__main__":
        print(f"Stage 4 JSON output: {json.dumps(stage3_data, indent=2)}")

    return baseline_runtime


if __name__ == "__main__":
    import sys

    run_stage4_run_timed_pass(
        sys.argv[1],
        sys.argv[2],
        int(sys.argv[3]),
    )