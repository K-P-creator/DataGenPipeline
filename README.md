#   Data Collection Script Structure

##  Main script

Runs the `per_benchmark.py` on each benchmark. After that finishes, appends the output data to a .csv that contains the entire dataset.

##  Run one script

Runs the 5 stage pipeline on one data source. 
    
### Stage 1

Generates a clang command and runs the compilation process to covert from C code to llvm IR.
 
### Stage 2

Interpolates a timer into the llvm bytecode to surround the main function. Timers will output to cout. 
    

### Stage 3

Runs the opt pass in data collection mode (Hot Loop Index == 0), and determines the number of loops. This pass will also serve to collect all of the features for each loop (except runtime). Output here is sent via cout. 


### Stage 4

Runs the timed pass with unroll factor set to 1. This will run `warmup_runs + timed_runs` number of times, and saves each time, including the median time. This median time will serve as a baseline for all the loops. 

### Stage 5

Runs loops `(warmup_runs + timed_runs) * len(unroll_factor)` number of times, and records the timer statistics per unroll factor per loop.
