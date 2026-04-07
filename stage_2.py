#   ### Stage 2
#   Interpolates a timer into the llvm bytecode to surround the main function.
#   Timers will output to stdout.
#
#   Input is the filename of the generated LLVM IR file.
#   Output is the SAME filename (modified in-place).

from pathlib import Path
import re


def run_stage2_interpolate_timer(llvm_ir_filename: str) -> str:
    input_path = Path(llvm_ir_filename)

    if not input_path.exists():
        raise FileNotFoundError(f"Stage 2 failed: IR file not found: {input_path}")

    ir_text = input_path.read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # Stage 2A: Add required declarations if missing
    # -------------------------------------------------------------------------
    additions = []

    if "%struct.timespec = type { i64, i64 }" not in ir_text:
        additions.append("%struct.timespec = type { i64, i64 }\n")

    if '@.my_timer_fmt = private unnamed_addr constant [17 x i8] c"TIMER_NS: %ld\\0A\\00\\n"' not in ir_text:
        additions.append('@.my_timer_fmt = private unnamed_addr constant [17 x i8] c"TIMER_NS: %ld\\0A\\00\\n"\n')

    if "declare i32 @clock_gettime(i32 noundef, ptr noundef)" not in ir_text:
        additions.append("declare i32 @clock_gettime(i32 noundef, ptr noundef)\n")

    if "declare i32 @printf(ptr noundef, ...)" not in ir_text:
        additions.append("declare i32 @printf(ptr noundef, ...)\n")

    triple_match = re.search(r'^(target triple = .*)$', ir_text, flags=re.MULTILINE)
    if not triple_match:
        raise RuntimeError("Stage 2 failed: could not find target triple line.")

    insert_pos = triple_match.end()
    ir_text = ir_text[:insert_pos] + "\n" + "".join(additions) + ir_text[insert_pos:]
    # -------------------------------------------------------------------------
    # Stage 2B: Locate main()
    # -------------------------------------------------------------------------
    main_match = re.search(
        r"(define\s+[^@]*@main\s*\([^)]*\)[^{]*\{)(.*?)(^\})",
        ir_text,
        flags=re.DOTALL | re.MULTILINE,
    )

    if not main_match:
        raise RuntimeError("Stage 2 failed: could not find main() definition.")

    main_header = main_match.group(1)
    main_body = main_match.group(2)
    main_footer = main_match.group(3)

    entry_match = re.search(r'(^entry:\s*$)', main_body, flags=re.MULTILINE)
    if not entry_match:
        raise RuntimeError("Stage 2 failed: could not find entry block in main().")

    

    # -------------------------------------------------------------------------
    # Stage 2C: Insert timer start at top of main
    # -------------------------------------------------------------------------
    entry_instrumentation = """
  %my_timer_start = alloca %struct.timespec, align 8
  %my_timer_end = alloca %struct.timespec, align 8
  %my_timer_start_call = call i32 @clock_gettime(i32 1, ptr %my_timer_start)
"""

    insert_pos = entry_match.end()
    instrumented_body = (
        main_body[:insert_pos]
        + entry_instrumentation
        + main_body[insert_pos:]
    )

    # -------------------------------------------------------------------------
    # Stage 2D: Insert timer end + print before each return
    # -------------------------------------------------------------------------
    return_counter = 0

    def replace_return(match: re.Match) -> str:
        nonlocal return_counter
        idx = return_counter
        return_counter += 1

        ret_line = match.group(0)

        instrumentation = f"""
  %my_timer_end_call_{idx} = call i32 @clock_gettime(i32 1, ptr %my_timer_end)
  %my_timer_start_val_{idx} = load %struct.timespec, ptr %my_timer_start, align 8
  %my_timer_end_val_{idx} = load %struct.timespec, ptr %my_timer_end, align 8

  %my_timer_start_sec_{idx} = extractvalue %struct.timespec %my_timer_start_val_{idx}, 0
  %my_timer_start_nsec_{idx} = extractvalue %struct.timespec %my_timer_start_val_{idx}, 1
  %my_timer_end_sec_{idx} = extractvalue %struct.timespec %my_timer_end_val_{idx}, 0
  %my_timer_end_nsec_{idx} = extractvalue %struct.timespec %my_timer_end_val_{idx}, 1

  %my_timer_start_sec_ns_{idx} = mul i64 %my_timer_start_sec_{idx}, 1000000000
  %my_timer_end_sec_ns_{idx} = mul i64 %my_timer_end_sec_{idx}, 1000000000

  %my_timer_start_total_ns_{idx} = add i64 %my_timer_start_sec_ns_{idx}, %my_timer_start_nsec_{idx}
  %my_timer_end_total_ns_{idx} = add i64 %my_timer_end_sec_ns_{idx}, %my_timer_end_nsec_{idx}

  %my_timer_elapsed_ns_{idx} = sub i64 %my_timer_end_total_ns_{idx}, %my_timer_start_total_ns_{idx}
  %my_timer_fmt_ptr_{idx} = getelementptr inbounds [5 x i8], ptr @.my_timer_fmt, i64 0, i64 0
  %my_timer_printf_{idx} = call i32 (ptr, ...) @printf(ptr %my_timer_fmt_ptr_{idx}, i64 %my_timer_elapsed_ns_{idx})
"""
        return instrumentation + ret_line

    instrumented_body = re.sub(
        r"^\s*ret\s+i32\s+.*$",
        replace_return,
        instrumented_body,
        flags=re.MULTILINE,
    )

    # -------------------------------------------------------------------------
    # Stage 2E: Rebuild and overwrite file
    # -------------------------------------------------------------------------
    new_main = main_header + instrumented_body + main_footer
    new_ir_text = ir_text[: main_match.start()] + new_main + ir_text[main_match.end() :]

    # WRITE BACK TO SAME FILE (in-place modification)
    input_path.write_text(new_ir_text, encoding="utf-8")

    print(f"Stage 2 Complete.\nTimer injected into: {input_path}")

    return str(input_path)


if __name__ == "__main__":
    import sys
    run_stage2_interpolate_timer(sys.argv[1])