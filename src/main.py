import sys
import random
import os
from pprint import PrettyPrinter
from DataLoader import DataLoader
from HardRestrictions import HardRestrictions
from Heuristic import heuristic_schedule
from SoftRestrictions import SoftRestrictions
from Schedule import *
from Brute import brute_force

from genetic_algorithm import run_genetic_algorithm

def usage():
    print("USAGE: python main.py <data-folder-path> [mode]")
    print("     - data-file-path: path to the input data directory")
    print("     - mode: how the solution is built (0=brute force, 1=heuristic, 2=genetic algorithm). 2 is default.")

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

    schedules = []

    if args.mode == 0:
        schedule = brute_force(loader)
        if schedule: schedules.append(schedule)
    elif args.mode == 1:
        schedule = heuristic_schedule(loader, hard_weight=1000.0, soft_weight=100.0, verbose=args.verbose)
        if schedule: schedules.append(schedule)
    elif args.mode == 2:
        # Devuelve una lista con los 10 mejores resultados obtenidos
        schedules = run_genetic_algorithm(
            loader, 
            population_size=200, 
            generations=500, 
            num_results=10, 
            verbose=args.verbose
        )

    if schedules:
        if not os.path.exists("out"):
            os.makedirs("out")

        # Iteramos sobre todos los horarios encontrados y los guardamos
        for i, schedule in enumerate(schedules):
            suffix = f"_{i+1}" if len(schedules) > 1 else ""
            
            groups = list(schedule.class_groups.values())
            hard_eval = HardRestrictions()
            detailed_report = hard_eval.get_detailed_report(groups)

            # Guardar reporte en archivo de texto numerado
            with open(f"out/hard_report{suffix}.txt", "w", encoding="utf-8") as f:
                for line in detailed_report:
                    f.write(line + "\n")

            # Solo imprimimos en consola el reporte del primer horario
            if i == 0:  
                if detailed_report:
                    for line in detailed_report:
                        print(line)
                else:
                    print("No hard violations found in the best schedule.")

            # Guardar JSON y CSV numerados
            schedule.to_json(f"out/schedule{suffix}.json")
            schedule.to_csv(f"out/schedule{suffix}.csv")
            
        print(f"\nSe han guardado {len(schedules)} opciones de horario en la carpeta 'out/'.")
    else:
        print("Error: No schedule was generated.")

if __name__ == "__main__":
    main()