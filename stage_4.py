#   ### Stage 4
#   Runs the timed pass with unroll factor set to 1. This will run
#   `warmup_runs + timed_runs` number of times, and saves each time,
#   including the median time. This median time will serve as a baseline
#   for all the loops.
#
#   Input:
#       benchmark_json_index: index into configs/benchmarks.json
#       llvm_ir_filename: path to the timed LLVM IR file
#       stage_3_json_filename: path to stage_3_output.json
#
#   Output:
#       path to the updated stage_3_output.json

from pathlib import Path
from statistics import median


def run_stage4_run_timed_pass(
    benchmark_json_index: int,
    llvm_ir_filename: str,
    stage_3_json_filename: str,
) -> str:
    import json
    import subprocess

    llvm_ir_path = Path(llvm_ir_filename)
    stage_3_json_path = Path(stage_3_json_filename)

    if not llvm_ir_path.exists():
        raise FileNotFoundError(f"Stage 4 failed: IR file not found: {llvm_ir_path}")

    if not stage_3_json_path.exists():
        raise FileNotFoundError(f"Stage 4 failed: Stage 3 JSON not found: {stage_3_json_path}")

    # -------------------------------------------------------------------------
    # Load configs
    # -------------------------------------------------------------------------
    with open("configs/benchmarks.json", "r", encoding="utf-8") as f:
        benchmarks_cfg = json.load(f)["benchmarks"]

    if benchmark_json_index < 0 or benchmark_json_index >= len(benchmarks_cfg):
        raise IndexError(
            f"Benchmark index {benchmark_json_index} out of range "
            f"(0 to {len(benchmarks_cfg) - 1})"
        )

    benchmark_info = benchmarks_cfg[benchmark_json_index]

    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    opt_path = global_cfg["opt_path"]
    llc_path = global_cfg["llc_path"]
    warmup_runs = int(global_cfg["warmup_runs"])
    timed_runs = int(global_cfg["timed_runs"])

    files_to_link = benchmark_info.get("files_to_link", [])
    run_args = benchmark_info.get("run_args", [])

    work_dir = Path(benchmark_info["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Load Stage 3 JSON
    # -------------------------------------------------------------------------
    with open(stage_3_json_path, "r", encoding="utf-8") as f:
        stage_3_data = json.load(f)

    # -------------------------------------------------------------------------
    # Generate filenames
    # -------------------------------------------------------------------------
    stripped_ir_path = llvm_ir_path.with_name(llvm_ir_path.stem + "-stripped.ll")
    object_path = llvm_ir_path.with_suffix(".o")
    exe_path = llvm_ir_path.with_suffix(".out")

    # -------------------------------------------------------------------------
    # Generate the strip debug IR command
    # -------------------------------------------------------------------------
    strip_cmd = [
        opt_path,
        "-strip-debug",
        str(llvm_ir_path),
        "-S",
        "-o",
        str(stripped_ir_path),
        "--my-unroll-factor=0",
        "--my-hot-loop-index=0",
    ]

    strip_result = subprocess.run(
        strip_cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if strip_result.returncode != 0:
        raise RuntimeError(
            "Stage 4 failed during strip-debug.\n"
            f"Command: {' '.join(strip_cmd)}\n"
            f"STDOUT:\n{strip_result.stdout}\n"
            f"STDERR:\n{strip_result.stderr}"
        )

    # -------------------------------------------------------------------------
    # Generate the object file with llc
    # -------------------------------------------------------------------------
    llc_cmd = [
        llc_path,
        str(stripped_ir_path),
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
    # Generate the executable and link with any necessary files
    # -------------------------------------------------------------------------
    clang_cmd = [
        "clang",
        "-no-pie",
        str(object_path),
    ]

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
            "Stage 4 failed during final executable link.\n"
            f"Command: {' '.join(clang_cmd)}\n"
            f"STDOUT:\n{clang_result.stdout}\n"
            f"STDERR:\n{clang_result.stderr}"
        )

    # -------------------------------------------------------------------------
    # Run the executable warmup_runs + timed_runs times
    # Capture TIMER_NS output and compute the median of timed runs
    # -------------------------------------------------------------------------
    total_runs = warmup_runs + timed_runs
    captured_times = []

    for run_idx in range(total_runs):
        run_cmd = [str(exe_path), *run_args]

        run_result = subprocess.run(
            run_cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            check=False,
        )

        if run_result.returncode != 0:
            raise RuntimeError(
                f"Stage 4 failed while running executable on iteration {run_idx}.\n"
                f"Command: {' '.join(run_cmd)}\n"
                f"STDOUT:\n{run_result.stdout}\n"
                f"STDERR:\n{run_result.stderr}"
            )

        timer_ns = None
        for line in run_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("TIMER_NS:"):
                timer_ns = int(line.split(":", 1)[1].strip())

        if timer_ns is None:
            raise RuntimeError(
                f"Stage 4 failed: no TIMER_NS output found on iteration {run_idx}.\n"
                f"STDOUT:\n{run_result.stdout}\n"
                f"STDERR:\n{run_result.stderr}"
            )

        captured_times.append(timer_ns)

    timed_only = captured_times[warmup_runs:]
    baseline_median = int(median(timed_only))

    # -------------------------------------------------------------------------
    # Save the baseline median into every loop's median_times_ns["1"]
    # -------------------------------------------------------------------------
    for loop_record in stage_3_data.get("loops", []):
        if "median_times_ns" not in loop_record:
            loop_record["median_times_ns"] = {}
        loop_record["median_times_ns"]["1"] = baseline_median

    stage_3_data["stage_4"] = {
        "warmup_runs": warmup_runs,
        "timed_runs": timed_runs,
        "all_times_ns": captured_times,
        "timed_times_ns": timed_only,
        "median_time_ns": baseline_median,
        "stripped_ir": str(stripped_ir_path),
        "object_file": str(object_path),
        "executable": str(exe_path),
    }

    with open(stage_3_json_path, "w", encoding="utf-8") as f:
        json.dump(stage_3_data, f, indent=2)

    print(
        "Stage 4 Complete.\n"
        f"Baseline median runtime (ns): {baseline_median}\n"
        f"Updated JSON: {stage_3_json_path}"
    )

    if __name__ == "__main__":
        print(f"Stage 4 JSON output: {json.dumps(stage_3_data, indent=2)}")

    return str(stage_3_json_path)


if __name__ == "__main__":
    import sys

    benchmark_json_index = int(sys.argv[1])
    llvm_ir_filename = sys.argv[2]
    stage_3_json_filename = sys.argv[3]

    run_stage4_run_timed_pass(
        benchmark_json_index,
        llvm_ir_filename,
        stage_3_json_filename,
    )