"""
gen_labeled_data.py

This script iterates through all the files in the data folder and generates a fully labelled, concatonated dataset in JSON format.

This will be re-run every time that there is more data added.

To start, this script first runs update_final_features in order to make sure everything is up to date.
"""

from pathlib import Path
import json

DATA_DIR = Path("data")
OUTPUT_PATH = Path("labeled_data/dataset.json")

def gen_labeled_data():
    #   Create a new datset file
    with open(OUTPUT_PATH, 'w', encoding="utf-8"):
        pass

    #   Make sure everything is up to date
    import update_final_features
    # update_final_features.update_final_features()

    #   Loop through each file in data
    for file in DATA_DIR.glob("*_final_results.json"):

        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print ("Labeleling file " + file.name)

        #   Loop through each loop in file
        for loop in data["loops"]:
            label = 0
            best_factor = 1

            #   positive iff any of the unroll factors cycles <= .98 * baseline cycles
            #   Prefer smaller unroll factors
            medians = loop["median_cycles"]
            baseline = medians["1"] * 0.98
            if medians["2"] <= baseline:
                label = 1
                best_factor = 2

            if medians["4"] <= baseline:
                label = 1
                if medians["4"] < medians["2"]:
                    best_factor = 4

            if medians["8"] <= baseline:
                label = 1
                if medians["8"] < medians["4"] and medians["8"] < medians["2"]:
                    best_factor = 8

            loop["label"] = label
            loop["best_factor"] = best_factor

            #   Strip uneccesary timing data
            del loop["loop_index"]
            del loop["median_times_seconds"]
            del loop["median_cycles"]
            del loop["timing_stats"]
            del loop["features"]["loop_location"]
            del loop["features"]["loop_range"]
            del loop["features"]["tripcount"]
            del loop["features"]["is_annotated_parallel"]
            del loop["features"]["is_loop_simplify_form"]
            del loop["features"]["is_rotated"]
            del loop["features"]["has_dedicated_exits"]
            
            #   Concat loop to dataset
            with open(OUTPUT_PATH, 'a', encoding="utf-8") as file:
                file.write(json.dumps(loop) + '\n')


if __name__ == "__main__":
    gen_labeled_data()
    print("Full labeled dataset generated at " + str(OUTPUT_PATH))
