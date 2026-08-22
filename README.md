# LLVM Runtime Loop-Unrolling Benchmark Pipeline

An automated benchmarking and data-generation pipeline for evaluating the
performance of runtime loop unrolling in LLVM.

This project works with a modified LLVM `LoopUnrollPass` to identify loops with
unknown compile-time trip counts, extract static loop features, force specific
runtime unroll factors, and measure the resulting performance.

The pipeline was built to answer the following question:

> Can compile-time loop characteristics predict when runtime loop unrolling
> will improve execution performance?

Companion LLVM fork:
[llvm-LUFG](https://github.com/K-P-creator/llvm-LUFG)

---

## Overview

The pipeline automates the full experiment:

1. Compile C benchmarks to LLVM IR.
2. Run the modified LLVM optimization pass to discover loops and collect
   compile-time features.
3. Generate a rolled baseline.
4. Recompile individual loops with forced unroll factors.
5. Execute each configuration under controlled CPU conditions.
6. Collect timing and hardware performance measurements.
7. Aggregate the results into a labeled dataset for analysis.

Benchmarks include workloads from PolyBench-C, TSVC, and additional synthetic
loops.

---

## Architecture

```text
C Benchmark
    |
    v
  Clang
    |
    v
 LLVM IR
    |
    v
Modified LoopUnrollPass
    |
    +----> Static Loop Features
    |
    v
Forced Unroll Factor
    |
    v
   LLVM IR
    |
    v
    llc
    |
    v
Executable
    |
    v
perf / taskset
    |
    v
Performance Results
    |
    v
Labeled Dataset
