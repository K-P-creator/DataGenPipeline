#   ### Stage 3
#   Runs the opt pass in data collection mode (Hot Loop Index == 0), and
#   determines the number of loops. This pass will also serve to collect
#   all of the features for each loop (except runtime). Output here is sent via stdout.
#
#   Input is the LLVM IR filename.
#   Output is the filename of stage_3_output.json.

def run_stage3_collect_loop_features(llvm_ir_filename: str, ) -> str:
    import subprocess
    from pathlib import Path
    import json

    indent = ""
    if __name__ != "__main__":
        indent = "\t"

    def parse_value(raw: str):
        raw = raw.strip()

        if raw == "True":
            return True
        if raw == "False":
            return False

        # int
        try:
            return int(raw)
        except ValueError:
            pass

        # float
        try:
            return float(raw)
        except ValueError:
            pass

        return raw

    def parse_last_dataset(stdout_text: str, unroll_factors: list[int]) -> dict:
        # Split on each dataset start and keep the last non-empty dataset
        parts = stdout_text.split("Loop Count:")
        dataset_chunks = [p.strip() for p in parts[1:] if p.strip()]
        if not dataset_chunks:
            raise RuntimeError("Stage 3 parse failed: no 'Loop Count:' dataset found in stdout.")

        last_chunk = dataset_chunks[-1]

        lines = [line.strip() for line in last_chunk.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Stage 3 parse failed: last dataset is empty.")

        # First line of the chunk is the loop count number
        loop_count = int(lines[0])

        # Everything after "Collected Loop Data:" contains loop records
        try:
            collected_idx = lines.index("Collected Loop Data:")
        except ValueError as exc:
            raise RuntimeError("Stage 3 parse failed: missing 'Collected Loop Data:' marker.") from exc

        record_lines = lines[collected_idx + 1:]

        loops = []
        current_loop = None

        for line in record_lines:
            if not line:
                continue

            if line.startswith("Loop Index:"):
                if current_loop is not None:
                    loops.append(current_loop)
                    loop_count

                loop_index = int(line.split(":", 1)[1].strip())
                current_loop = {
                    "loop_index": loop_index,
                    "features": {},
                }
                continue

            if current_loop is None:
                continue

            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            normalized_key = key.strip().lower().replace(" ", "_")
            current_loop["features"][normalized_key] = parse_value(value)

        if current_loop is not None:
            loops.append(current_loop)

        return {
            "loop_count": loop_count,
            "loops": loops,
        }, loop_count

    input_path = Path(llvm_ir_filename)

    if not input_path.exists():
        raise FileNotFoundError(f"Stage 3 failed: IR file not found: {input_path}")

    # Import the global configuration to get the opt path and pass pipeline
    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    opt_path = global_cfg["opt_path"]
    opt_passes = global_cfg["opt_passes"]
    opt_common_flags = global_cfg["opt_common_flags"]
    unroll_factors = global_cfg["unroll_factors"]

    # Data collection mode
    unroll_factor = 1
    hot_loop_index = 0

    output_ir_filename = input_path.with_name(input_path.stem + "_data_mode_opt.ll")
    output_json_filename = input_path.parent / "stage_3_output.json"

    # Build opt command
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
        str(output_ir_filename),
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

    parsed_output, loop_count = parse_last_dataset(result.stdout, unroll_factors)

    # Save stage 3 dataset
    with open(output_json_filename, "w", encoding="utf-8") as f:
        json.dump(parsed_output, f, indent=2)

    print(
        indent +
        "Stage 3 Complete.\n" +
        indent +
        f"Loop feature collection output IR: {output_ir_filename}\n" +
        indent +
        "Stage 3 dataset saved to JSON file: "
            f"{output_json_filename}" +
        indent +
        f"Number of loops: {loop_count}"
    )

    if __name__ == "__main__":
        print(
            f"Stage 3 JSON output: {json.dumps(parsed_output, indent=2)}"
        )

    return str(output_json_filename), str(output_ir_filename), loop_count


if __name__ == "__main__":
    import sys
    llvm_ir_filename = sys.argv[1]
    run_stage3_collect_loop_features(llvm_ir_filename)