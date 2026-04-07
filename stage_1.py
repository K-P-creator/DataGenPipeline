#   ### Stage 1
#   Generates a clang command and runs the compilation process to covert from C 
#   code to llvm IR.

#   Input is the index of the benchmark in the benchmarks.json file.
#   Output is the filename of the generated llvm IR file.


def run_stage1_generate_ir(benchmark_json_index: int) -> str:
    import json
    import subprocess
    from pathlib import Path

    # Load benchmark info from the index
    with open("configs/benchmarks.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    benchmarks = data["benchmarks"]
    benchmark_info = benchmarks[benchmark_json_index]

    # Load global configuration from global_configs.json
    with open("configs/global_configs.json", "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    # Resolve benchmark paths
    source_dir = Path(benchmark_info["source_dir"])
    work_dir = Path(benchmark_info["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    source_file = source_dir / benchmark_info["source_file"]
    output_ir = work_dir / benchmark_info["output_ir"]

    # Build the clang command
    cmd = [global_cfg["clang_path"]]

    # Add common clang IR-generation flags from globals.json
    cmd.extend(global_cfg["clang_ir_flags"])

    # Add include directories
    for inc in benchmark_info.get("include_dirs", []):
        cmd.extend(["-I", inc])

    # Add main source file
    cmd.append(str(source_file))

    # Add any extra source files
    for extra_src in benchmark_info.get("extra_sources", []):
        cmd.append(str(source_dir / extra_src))

    # Add output IR path and target triple
    cmd.extend(["-o", str(output_ir)])
    cmd.extend(["-target", global_cfg["target_triple"]])

    # Run the clang command from the source directory so relative includes work
    result = subprocess.run(
        cmd,
        cwd=str(source_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Stage 1 failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    print(f"Stage 1 completed successfully.\nGenerated IR at: {output_ir}")
    if __name__ == "__main__":
        print(f"\nGenerated clang command: {' '.join(cmd)}\n")

    return str(output_ir)


if __name__ == "__main__":
    import sys
    run_stage1_generate_ir(int(sys.argv[1]))
