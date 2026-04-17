#   Runs the 5 stage pipeline on one data source.

#   Input is the json string containing all the per benchmark info.
#
#   This is the main entry point for the per benchmark data collection process.
#   Each stage will be implemented in a sub-script, called in sequence here.
#   
#   Outputs a .json file containing all of the collected data for the benchmark.
#
#   The 5 stages are as follows:
#   
#   ### Stage 1
#   Generates a clang command and runs the compilation process to covert from C 
#   code to llvm IR.
#   
#   ### Stage 2 - DEPRECATED - I will use perf instead now
#   Interpolates a timer into the llvm bytecode to surround the main function. 
#   Timers will output to cout.
#   
#   ### Stage 3
#   Runs the opt pass in data collection mode (Hot Loop Index == 0), and 
#   determines the number of loops. This pass will also serve to collect 
#   all of the features for each loop (except runtime). Output here is sent via cout.
#   
#   ### Stage 4
#   Runs the timed pass with unroll factor set to 1. This will run 
#   `warmup_runs + timed_runs` number of times, and saves each time, 
#   including the median time. This median time will serve as a baseline 
#   for all the loops.
#   
#   ### Stage 5
#   Runs loops `(warmup_runs + timed_runs) * len(unroll_factor)` number of times, 
#   and records the timer statistics per unroll factor per loop.
#


#   Stage module imports
import stage_1
import stage_2
import stage_3
import stage_4
import stage_5

from pathlib import Path


def run_per_benchmark(benchmark_json_index: int) -> Path:

    # Stage 1: Generate clang command and compile to LLVM IR. Input is index to benchmark JSON
    llvm_IR_filename = stage_1.run_stage1_generate_ir(benchmark_json_index)
    print("") # \n

    #   DEPRECATED  
    # Stage 2: Interpolate timer into LLVM bytecode
    #   stage_2.run_stage2_interpolate_timer(llvm_IR_filename)
    #   print("") # \n

    # Stage 3: Run opt pass in data collection mode to determine loop features
    data_mode_opt_pass_filename = stage_3.run_stage3_collect_loop_features(llvm_IR_filename)
    print("") # \n

    ## Stage 4: Run timed pass with unroll factor 1 to get baseline runtime
    baseline_runtime = stage_4.run_stage4_run_timed_pass(data_mode_opt_pass_filename, llvm_IR_filename, benchmark_json_index)
    print("") # \n

    ## Stage 5: Run loops with various unroll factors and record timing statistics
    final_results_path = stage_5.run_stage5_run_unroll_and_time(data_mode_opt_pass_filename, llvm_IR_filename, benchmark_json_index)
    print("") # \n

    return final_results_path


if __name__ == "__main__":
    import sys
    run_per_benchmark(int(sys.argv[1]))
