from pathlib import Path
from statistics import median


def run_stage4_run_timed_pass(
    data_mode_opt_pass_filename: str,
    llvm_IR_filename: str,
    benchmark_json_index: int,
) -> float:
    import json
    import subprocess

    indent = ""
    if __name__ != "__main__":
        indent = "\t"

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
    link_flags = benchmark_info.get("link_flags", [])

    # Allow either:
    #   "link_flags": "-lm"
    # or
    #   "link_flags": ["-lm", "-pthread"]
    if isinstance(link_flags, str):
        link_flags = [link_flags]
    elif not isinstance(link_flags, list):
        raise TypeError(
            f"Stage 4 failed: link_flags must be a string or list, got {type(link_flags)}"
        )

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

    clang_cmd.extend(link_flags)
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
    # Helpers for parsing perf output
    # -------------------------------------------------------------------------
    def parse_perf_output(stderr_text: str) -> tuple[float, int]:
        elapsed_seconds = None
        cycles = None

        for raw_line in stderr_text.splitlines():
            line = raw_line.strip()

            if "cycles" in line:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "cycles":
                    cycle_str = parts[0].replace(",", "")
                    cycles = int(cycle_str)

            if line.endswith("seconds time elapsed"):
                parts = line.split()
                if len(parts) >= 4:
                    elapsed_seconds = float(parts[0])

        if elapsed_seconds is None:
            raise RuntimeError(
                "Could not parse 'seconds time elapsed' from perf output.\n"
                f"STDERR:\n{stderr_text}"
            )

        if cycles is None:
            raise RuntimeError(
                "Could not parse 'cycles' from perf output.\n"
                f"STDERR:\n{stderr_text}"
            )

        return elapsed_seconds, cycles

    # -------------------------------------------------------------------------
    # Run executable with perf and collect timing/cycles
    # -------------------------------------------------------------------------
    total_runs = warmup_runs + timed_runs
    all_times_seconds = []
    all_cycles = []

    for i in range(total_runs):
        print (indent + f"Running Run {i}")

        run_cmd = [
            "taskset",
            "-c",
            "3",
            "perf",
            "stat",
            "-e",
            "cycles",
            str(exe_path),
            *run_args,
        ]

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
                f"Command: {' '.join(run_cmd)}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        elapsed_seconds, cycles = parse_perf_output(result.stderr)

        all_times_seconds.append(elapsed_seconds)
        all_cycles.append(cycles)

    timed_only_seconds = all_times_seconds[warmup_runs:]
    timed_only_cycles = all_cycles[warmup_runs:]

    baseline_runtime_seconds = float(median(timed_only_seconds))
    baseline_cycles = int(median(timed_only_cycles))

    # -------------------------------------------------------------------------
    # Update Stage 3 JSON
    # -------------------------------------------------------------------------
    with open(stage3_json_path, "r", encoding="utf-8") as f:
        stage3_data = json.load(f)

    for loop in stage3_data.get("loops", []):
        loop.setdefault("median_times_seconds", {})
        loop.setdefault("median_cycles", {})
        loop["median_times_seconds"]["1"] = baseline_runtime_seconds
        loop["median_cycles"]["1"] = baseline_cycles

    stage3_data["stage_4"] = {
        "baseline_runtime_seconds": baseline_runtime_seconds,
        "baseline_cycles": baseline_cycles,
        "all_times_seconds": all_times_seconds,
        "all_cycles": all_cycles,
    }

    with open(stage3_json_path, "w", encoding="utf-8") as f:
        json.dump(stage3_data, f, indent=2)

    print(
        "\n" +
        indent +
        f"Stage 4 complete. Baseline runtime: {baseline_runtime_seconds} s, "
        f"baseline cycles: {baseline_cycles}"
    )

    if __name__ == "__main__":
        print(f"Stage 4 JSON output: {json.dumps(stage3_data, indent=2)}")

    return baseline_runtime_seconds


if __name__ == "__main__":
    import sys

    run_stage4_run_timed_pass(
        sys.argv[1],
        sys.argv[2],
        int(sys.argv[3]),
    )