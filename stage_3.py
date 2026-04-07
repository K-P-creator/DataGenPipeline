#   ### Stage 3
#   Runs the opt pass in data collection mode (Hot Loop Index == 0), and
#   determines the number of loops. This pass will also serve to collect
#   all of the features for each loop (except runtime). Output here is sent via stdout.

def run_stage3_collect_loop_features(llvm_ir_filename: str) -> str:
    import subprocess
    from pathlib import Path
    import json

    input_path = Path(llvm_ir_filename)

    if not input_path.exists():
        raise FileNotFoundError(f"Stage 3 failed: IR file not found: {input_path}")

    # Import the global configuration to get the opt path and pass pipeline
    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    opt_path = global_cfg["opt_path"]
    opt_passes = global_cfg["opt_passes"]
    opt_common_flags = global_cfg["opt_common_flags"]

    unroll_factor = 1
    hot_loop_index = 0

    output_filename = input_path.with_name(input_path.stem + "_data_mode_opt.ll")

    # Build opt command as a list
    cmd = [
        opt_path,
        f"-passes={opt_passes}",
        str(input_path),
    ]

    cmd.extend(opt_common_flags)
    cmd.extend([
        f"--my-unroll-factor={unroll_factor}",
        f"--my-hot-loop-index={hot_loop_index}",
        "-o",
        str(output_filename),
    ])

    result = subprocess.run(
        cmd,
        cwd=str(input_path.parent),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Stage 3 failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    print(f"Stage 3 Complete.\nLoop feature collection output IR: {output_filename}")

    # If you later want to parse stdout for loop feature JSON lines,
    # result.stdout is where to do it.

    if __name__ == "__main__":
        print("Stage 3 raw stdout from opt pass:")
        print(result.stdout)

    return str(output_filename)


if __name__ == "__main__":
    import sys
    run_stage3_collect_loop_features(sys.argv[1])