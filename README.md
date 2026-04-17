#   Data Collection Script Structure

##  Usage

First, set your CPU clock to a constant level using

`sudo cpupower frequency-set -d <target-frequency>GHz`

and

`sudo cpupower frequency-set -u <target-frequency>GHz`

Then, run the script with

`python3 collect_all_data.py`

Or, run each test individually with

`python3 per_benchmark.py <benchmark index`

You can also monitor system temps with

`watch -n 1 sensors`

In order to catch any sort of thermal throttling. In this event, simply turn down the clockrate, and adjust fans to max. 

---

##  Main script

Runs the `per_benchmark.py` on each benchmark. After that finishes, appends the output data to a .csv that contains the entire dataset.

##  Run one script

Runs the 5 stage pipeline on one data source. 
    
### Stage 1

Generates a clang command and runs the compilation process to covert from C code to llvm IR.
 
### Stage 2

**Stage 2 has been deprecated**. I now will use perf timer and cycle counter for perf metrics. 

Interpolates a timer into the llvm bytecode to surround the main function. Timers will output to cout. 
    
### Stage 3

Runs the opt pass in data collection mode (Hot Loop Index == 0), and determines the number of loops. This pass will also serve to collect all of the features for each loop (except runtime). Output here is sent via cout. 

### Stage 4

Runs the timed pass with unroll factor set to 1. This will run `warmup_runs + timed_runs` number of times, and saves each time, including the median time. This median time will serve as a baseline for all the loops. 

### Stage 5

Runs loops `(warmup_runs + timed_runs) * len(unroll_factor)` number of times, and records the timer statistics per unroll factor per loop.

---

##  Configs

Right now the configs contain mostly flags to be used when running stages. They also contain some options to be used when collecting data. The default warmup runs has been changed to 2, with the runs per loop updated to 10. So we run each test 12 times, throw out the first two runs, then take the median of the remaining 10. 

I have also baked in to the script an extra perfomance considerations. I am pinning to CPU core 3.
