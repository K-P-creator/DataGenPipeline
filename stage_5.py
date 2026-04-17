from pathlib import Path
from statistics import median, stdev


def run_stage5_run_unroll_and_time(
    data_mode_opt_pass_filename: str,
    llvm_IR_filename: str,
    benchmark_json_index: int,
) -> str:
    import json
    import subprocess

    indent = ""
    if __name__ != "__main__":
        indent = "\t"

    stage3_json_path = Path(data_mode_opt_pass_filename)
    llvm_ir_path = Path(llvm_IR_filename)

    if not stage3_json_path.exists():
        raise FileNotFoundError(
            f"Stage 5 failed: Stage 3 JSON file not found: {stage3_json_path}"
        )

    if not llvm_ir_path.exists():
        raise FileNotFoundError(
            f"Stage 5 failed: LLVM IR file not found: {llvm_ir_path}"
        )

    # -------------------------------------------------------------------------
    # Load configs
    # -------------------------------------------------------------------------
    with open("configs/benchmarks.json", "r", encoding="utf-8") as f:
        benchmarks = json.load(f)["benchmarks"]

    if benchmark_json_index < 0 or benchmark_json_index >= len(benchmarks):
        raise IndexError(
            f"Benchmark index {benchmark_json_index} out of range "
            f"(0 to {len(benchmarks) - 1})"
        )

    benchmark_info = benchmarks[benchmark_json_index]

    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    opt_path = global_cfg["opt_path"]
    llc_path = global_cfg["llc_path"]
    warmup_runs = int(global_cfg["warmup_runs"])
    timed_runs = int(global_cfg["timed_runs"])
    unroll_factors = [int(x) for x in global_cfg["unroll_factors"] if int(x) != 1]
    perm_path = Path(global_cfg["perm_path"])

    work_dir = Path(benchmark_info["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)
    perm_path.mkdir(parents=True, exist_ok=True)

    files_to_link = benchmark_info.get("files_to_link", [])
    run_args = benchmark_info.get("run_args", [])
    link_flags = benchmark_info.get("link_flags", [])
    source_dir = Path(benchmark_info["source_dir"])
    benchmark_name = benchmark_info["name"]

    # Allow either:
    #   "link_flags": "-lm"
    # or
    #   "link_flags": ["-lm", "-pthread"]
    if isinstance(link_flags, str):
        link_flags = [link_flags]
    elif not isinstance(link_flags, list):
        raise TypeError(
            f"Stage 5 failed: link_flags must be a string or list, got {type(link_flags)}"
        )

    # -------------------------------------------------------------------------
    # Load Stage 3 JSON
    # -------------------------------------------------------------------------
    with open(stage3_json_path, "r", encoding="utf-8") as f:
        stage3_data = json.load(f)

    loops = stage3_data.get("loops", [])
    if not loops:
        raise RuntimeError("Stage 5 failed: no loops found in stage 3 JSON.")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def run_subprocess_cmd(cmd: list[str], cwd: Path, fail_msg: str):
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{fail_msg}\n"
                f"Command: {' '.join(cmd)}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
        return result

    def parse_perf_output(stderr: str) -> tuple[float, int]:
        elapsed_seconds = None
        cycles = None

        for raw_line in stderr.splitlines():
            line = raw_line.strip()

            if "cycles" in line:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "cycles":
                    cycles = int(parts[0].replace(",", ""))

            if line.endswith("seconds time elapsed"):
                parts = line.split()
                if len(parts) >= 4:
                    elapsed_seconds = float(parts[0])

        if elapsed_seconds is None:
            raise RuntimeError(
                "Stage 5 failed: could not parse 'seconds time elapsed' from perf output.\n"
                f"STDERR:\n{stderr}"
            )

        if cycles is None:
            raise RuntimeError(
                "Stage 5 failed: could not parse 'cycles' from perf output.\n"
                f"STDERR:\n{stderr}"
            )

        return elapsed_seconds, cycles

    def summarize_float(values: list[float]) -> dict:
        if not values:
            raise RuntimeError("Stage 5 failed: cannot summarize empty float list.")

        summary = {
            "median": float(median(values)),
            "min": float(min(values)),
            "max": float(max(values)),
            "num_timed_runs": len(values),
        }

        if len(values) >= 2:
            summary["stdev"] = float(stdev(values))
        else:
            summary["stdev"] = 0.0

        return summary

    def summarize_int(values: list[int]) -> dict:
        if not values:
            raise RuntimeError("Stage 5 failed: cannot summarize empty int list.")

        summary = {
            "median": int(median(values)),
            "min": int(min(values)),
            "max": int(max(values)),
            "num_timed_runs": len(values),
        }

        if len(values) >= 2:
            summary["stdev"] = float(stdev(values))
        else:
            summary["stdev"] = 0.0

        return summary

    # -------------------------------------------------------------------------
    # Loop through each unroll factor (except 1) and each loop
    # -------------------------------------------------------------------------
    for factor in unroll_factors:
        print(indent + f"Running unroll factor {factor}")
        for loop_record in loops:
            loop_index = int(loop_record["loop_index"])

            factor_ir_path = work_dir / f"{benchmark_name}_loop_{loop_index}_factor_{factor}.ll"
            object_path = work_dir / f"{benchmark_name}_loop_{loop_index}_factor_{factor}.o"
            exe_path = work_dir / f"{benchmark_name}_loop_{loop_index}_factor_{factor}.out"

            # -------------------------------------------------------------
            # Generate IR with opt using --my-unroll-factor and --my-hot-loop-index
            # -------------------------------------------------------------
            opt_cmd = [
                opt_path,
                f"-passes={global_cfg['opt_passes']}",
                str(llvm_ir_path),
            ]

            opt_cmd.extend(global_cfg.get("opt_common_flags", []))
            opt_cmd.extend([
                f"--my-unroll-factor={factor}",
                f"--my-hot-loop-index={loop_index}",
                "-o",
                str(factor_ir_path),
            ])

            run_subprocess_cmd(
                opt_cmd,
                work_dir,
                f"Stage 5 failed during opt for loop {loop_index}, factor {factor}.",
            )

            # -------------------------------------------------------------
            # Compile IR to object with llc
            # -------------------------------------------------------------
            llc_cmd = [
                llc_path,
                str(factor_ir_path),
                "-filetype=obj",
                "-o",
                str(object_path),
            ]

            run_subprocess_cmd(
                llc_cmd,
                work_dir,
                f"Stage 5 failed during llc for loop {loop_index}, factor {factor}.",
            )

            # -------------------------------------------------------------
            # Link executable with clang, files_to_link, and optional link_flags
            # -------------------------------------------------------------
            clang_cmd = ["clang", "-no-pie", str(object_path)]

            for file_to_link in files_to_link:
                clang_cmd.append(str(source_dir / file_to_link))

            clang_cmd.extend(link_flags)
            clang_cmd.extend(["-o", str(exe_path)])

            run_subprocess_cmd(
                clang_cmd,
                work_dir,
                f"Stage 5 failed during link for loop {loop_index}, factor {factor}.",
            )

            # -------------------------------------------------------------
            # Run executable with taskset + perf and capture elapsed time/cycles
            # -------------------------------------------------------------
            total_runs = warmup_runs + timed_runs
            all_times_seconds = []
            all_cycles = []

            for run_idx in range(total_runs):
                run_cmd = [
                    "taskset",
                    "-c",
                    "3",
                    "perf",
                    "stat",
                    "--no-big-num",
                    "-e",
                    "cycles",
                    str(exe_path),
                    *run_args,
                ]

                print(indent + f"\tRunning Run {run_idx}")

                run_result = subprocess.run(
                    run_cmd,
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if run_result.returncode != 0:
                    raise RuntimeError(
                        f"Stage 5 failed while executing benchmark for loop {loop_index}, "
                        f"factor {factor}, run {run_idx}.\n"
                        f"Command: {' '.join(run_cmd)}\n"
                        f"STDOUT:\n{run_result.stdout}\n"
                        f"STDERR:\n{run_result.stderr}"
                    )

                elapsed_seconds, cycles = parse_perf_output(run_result.stderr)
                all_times_seconds.append(elapsed_seconds)
                all_cycles.append(cycles)

            timed_only_seconds = all_times_seconds[warmup_runs:]
            timed_only_cycles = all_cycles[warmup_runs:]

            time_summary = summarize_float(timed_only_seconds)
            cycle_summary = summarize_int(timed_only_cycles)

            median_runtime_seconds = time_summary["median"]
            median_cycles = cycle_summary["median"]

            print(
                indent +
                f"Unroll factor {factor}, loop {loop_index} complete.\n" +
                indent +
                f"Median runtime: {median_runtime_seconds} s, "
                f"Median cycles: {median_cycles}\n"
            )

            # -------------------------------------------------------------
            # Save compact timing stats into stage 3 JSON structure
            # -------------------------------------------------------------
            loop_record.setdefault("median_times_seconds", {})
            loop_record.setdefault("median_cycles", {})

            loop_record["median_times_seconds"][str(factor)] = median_runtime_seconds
            loop_record["median_cycles"][str(factor)] = median_cycles

            loop_record.setdefault("timing_stats", {})
            loop_record["timing_stats"][str(factor)] = {
                "time_seconds": {
                    "median": time_summary["median"],
                    "min": time_summary["min"],
                    "max": time_summary["max"],
                    "stdev": time_summary["stdev"],
                    "num_timed_runs": time_summary["num_timed_runs"],
                },
                "cycles": {
                    "median": cycle_summary["median"],
                    "min": cycle_summary["min"],
                    "max": cycle_summary["max"],
                    "stdev": cycle_summary["stdev"],
                    "num_timed_runs": cycle_summary["num_timed_runs"],
                },
            }

    # -------------------------------------------------------------------------
    # Save final JSON to permanent directory
    # -------------------------------------------------------------------------
    final_output_path = perm_path / f"{benchmark_name}_final_results.json"

    stage3_data["stage_5"] = {
        "completed_unroll_factors": unroll_factors,
        "final_output_path": str(final_output_path),
    }

    with open(final_output_path, "w", encoding="utf-8") as f:
        json.dump(stage3_data, f, indent=2)

    print(
        indent + 
        "\nStage 5 Complete.\n" +
        indent +
        f"Final results JSON: {final_output_path}"
    )

    if __name__ == "__main__":
        print(f"Stage 5 JSON output: {json.dumps(stage3_data, indent=2)}")

    # -------------------------------------------------------------------------
    # Cleanup: delete contents of work_dir (temp directory)
    # -------------------------------------------------------------------------
    print(indent + f"Cleaning up temp directory: {work_dir}")

    for item in work_dir.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
        except Exception as e:
            print(indent + f"Warning: Failed to delete {item}: {e}")

    return str(final_output_path)


if __name__ == "__main__":
    import sys

    data_mode_opt_pass_filename = sys.argv[1]
    llvm_ir_filename = sys.argv[2]
    benchmark_json_index = int(sys.argv[3])

    run_stage5_run_unroll_and_time(
        data_mode_opt_pass_filename,
        llvm_ir_filename,
        benchmark_json_index,
    )