#   ### Stage 5
#   Runs loops `(warmup_runs + timed_runs) * len(unroll_factor)` number of times,
#   and records the timer statistics per unroll factor per loop.
#
#   Loop through each unroll factor (except 1) and each loop, and generate an IR file
#   with opt using flags --my-unroll-factor and --my-hot-loop-index. Then compile, run,
#   and capture timer output, parse, and save timing statistics to the JSON from stage 3,
#   making sure to ignore the warmup runs.
#
#   The final JSON will be saved to a permanent directory (not the temp directory) with name
#   <benchmark_name>_final_results.json
#
#   Final directory is included in global configs as "perm_path"
#   This will be the timing data for each loop at each unroll factor.

from pathlib import Path
from statistics import median


def run_stage5_run_unroll_and_time(
    data_mode_opt_pass_filename: str,
    llvm_IR_filename: str,
    benchmark_json_index: int,
) -> str:
    import json
    import subprocess
    import shutil

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
    source_dir = Path(benchmark_info["source_dir"])
    benchmark_name = benchmark_info["name"]

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
    def run_cmd(cmd, cwd: Path, fail_msg: str):
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

    def parse_timer_ns(stdout: str) -> int:
        timer_val = None
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("TIMER_NS:"):
                timer_val = int(line.split(":", 1)[1].strip())
        if timer_val is None:
            raise RuntimeError(f"Stage 5 failed: TIMER_NS output not found.\nSTDOUT:\n{stdout}")
        return timer_val

    # -------------------------------------------------------------------------
    # Loop through each unroll factor (except 1) and each loop
    # -------------------------------------------------------------------------
    for factor in unroll_factors:
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

            run_cmd(opt_cmd, work_dir, f"Stage 5 failed during opt for loop {loop_index}, factor {factor}.")

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

            run_cmd(llc_cmd, work_dir, f"Stage 5 failed during llc for loop {loop_index}, factor {factor}.")

            # -------------------------------------------------------------
            # Link executable with clang and files_to_link
            # -------------------------------------------------------------
            clang_cmd = ["clang", "-no-pie", str(object_path)]

            for file_to_link in files_to_link:
                clang_cmd.append(str(source_dir / file_to_link))

            clang_cmd.extend(["-o", str(exe_path)])

            run_cmd(clang_cmd, work_dir, f"Stage 5 failed during link for loop {loop_index}, factor {factor}.")

            # -------------------------------------------------------------
            # Run executable and capture timing
            # -------------------------------------------------------------
            total_runs = warmup_runs + timed_runs
            all_times_ns = []

            for run_idx in range(total_runs):
                run_result = subprocess.run(
                    [str(exe_path), *run_args],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if run_result.returncode != 0:
                    raise RuntimeError(
                        f"Stage 5 failed while executing benchmark for loop {loop_index}, "
                        f"factor {factor}, run {run_idx}.\n"
                        f"STDOUT:\n{run_result.stdout}\n"
                        f"STDERR:\n{run_result.stderr}"
                    )

                all_times_ns.append(parse_timer_ns(run_result.stdout))

            timed_only_ns = all_times_ns[warmup_runs:]
            median_runtime_ns = int(median(timed_only_ns))

            # -------------------------------------------------------------
            # Save timing stats into stage 3 JSON structure
            # -------------------------------------------------------------
            loop_record.setdefault("median_times_ns", {})
            loop_record["median_times_ns"][str(factor)] = median_runtime_ns

            loop_record.setdefault("timing_stats_ns", {})
            loop_record["timing_stats_ns"][str(factor)] = {
                "all_times_ns": all_times_ns,
                "timed_only_ns": timed_only_ns,
                "median_time_ns": median_runtime_ns,
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
        "Stage 5 Complete.\n"
        f"Final results JSON: {final_output_path}"
    )

    if __name__ == "__main__":
        print(f"Stage 5 JSON output: {json.dumps(stage3_data, indent=2)}")

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
    