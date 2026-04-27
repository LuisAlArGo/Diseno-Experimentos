import sys
import random
import os
from pprint import PrettyPrinter
from DataLoader import DataLoader
from HardRestrictions import HardRestrictions
from Heuristic import heuristic_schedule
from SoftRestrictions import SoftRestrictions
# from Group import Group
from Schedule import *
from Brute import brute_force

from genetic_algorithm import run_genetic_algorithm


def usage():
    print("USAGE: python main.py <data-folder-path> [mode]")
    print("     - data-file-path: path to the input data directory")
    print("     - mode: how the solution is built (0=brute force, 1=heuristic, 2=genetic algorithm). 2 is default.")

def placeholder_schedule(loader: DataLoader) -> Schedule:
    """
    Build a placeholder schedule using a random assignment.
    
    Args:
        loader (DataLoader): data loader with input data
    
    Retruns:
        Schedule: generated schedule
    """
    schedule = build_random_schedule(loader)

    groups = list(schedule.class_groups.values())
    hard_eval = HardRestrictions()
    total_hard, hard_details = hard_eval.evaluate(groups)
    schedule.hard_violations = total_hard

    soft_eval = SoftRestrictions()
    soft_penalty, soft_details = soft_eval.evaluate(groups)
    schedule.soft_violations = soft_details

    hard_weight = 1000.0
    soft_weight = 100.0
    schedule.fitness_val = (total_hard * hard_weight) + (soft_penalty * soft_weight)

    return schedule


def main():
    import argparse
    parser = argparse.ArgumentParser(description="UCR Course Scheduler")
    parser.add_argument('--data-path', type=str, required=True,
                        help='Path to the data directory')
    parser.add_argument('--mode', type=int, choices=[0, 1, 2], default=2,
                        help='Mode of operation: 0=brute force, 1=heuristic, 2=genetic algorithm (default)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output for genetic algorithm and heuristic modes')
    args = parser.parse_args()    

    random.seed()
    loader = DataLoader(args.data_path)
    try:
        loader.load_all()
    except Exception as e:
        print(f"Error loading data: {e}")
        return
    print(f"Data Loaded: {len(loader.courses)} courses, {len(loader.professors)} professors, {len(loader.classrooms)} classrooms.")

    schedule = None

    if args.mode == 0:
        schedule = brute_force(loader)
    elif args.mode == 1:
        schedule = heuristic_schedule(loader, hard_weight=1000.0, soft_weight=100.0, verbose=args.verbose)
    elif args.mode == 2:
        schedule = run_genetic_algorithm(
            loader, 
            population_size=200, 
            generations=150, 
            verbose=args.verbose
        )

    if schedule:
        groups = list(schedule.class_groups.values())

        hard_eval = HardRestrictions()
        detailed_report = hard_eval.get_detailed_report(groups)

        # Guardar reporte en archivo
        if not os.path.exists("out"):
            os.makedirs("out")

        with open("out/hard_report.txt", "w", encoding="utf-8") as f:
            for line in detailed_report:
                f.write(line + "\n")

        if detailed_report:
            for line in detailed_report:
                print(line)
        else:
            print("No hard violations found.")

        schedule.to_json("out/schedule.json")
        schedule.to_csv("out/schedule.csv")
    else:
        print("Error: No schedule was generated.")

if __name__ == "__main__":
    main()