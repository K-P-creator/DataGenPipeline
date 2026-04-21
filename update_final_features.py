"""
update_final_features.py

This script is used when introducing new features to the dataset.

It will re-run stage3, generating the new output features from llvm, then add them into the final dataset.

This is useful to update features without having to run benchmarks again.
"""

from pathlib import Path
import json

DATA_DIR = Path("data")
CONFIGS_DIR = Path("configs/benchmarks.json")

def get_benchmark_index(name: str) -> int:
    with open(CONFIGS_DIR, "r", encoding="utf-8") as f:
        data = json.load(f)

    for i in range(len(data["benchmarks"])):
        if data["benchmarks"][i]["name"] == name:
            return i

    return -1

def update_final_features():
    import stage_1
    import stage_3

    indent = ""
    if __name__ != "__main__":
        indent = "\t"
    
    changed = 0
    
    for file in DATA_DIR.glob("*_final_results.json"):
        
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)

        benchmark_name = file.stem.replace("_final_results", "")
        benchmark_index = get_benchmark_index(benchmark_name)
        
        stage_1_output = stage_1.run_stage1_generate_ir(benchmark_index)
        stage_3_json, stage_3_ir, loop_count = stage_3.run_stage3_collect_loop_features(stage_1_output)

        with open(stage_3_json, "r", encoding="utf-8") as f:
            stage_3_data = json.load(f)

        for loop in stage_3_data["loops"]:
            new_features = loop["features"]
            old_features = data["loops"][loop["loop_index"] - 1]["features"]

            for feature in new_features:
                if feature not in old_features:
                    changed += 1
                    old_features[feature] = new_features[feature]
                    print (f"added {feature} to dataset")
                    
            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
       
    print(f"Added {changed} new features.")

update_final_features()
