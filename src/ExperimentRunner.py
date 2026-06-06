import os
import csv
import time
import shutil
import random
import traceback
from datetime import datetime
from DataLoader import DataLoader
from genetic_algorithm import run_genetic_algorithm

# Construye horarios aleatorios de momento
def run_simulated_annealing(loader, verbose=False):
    from Schedule import build_random_schedule
    schedule = build_random_schedule(loader)
    return [schedule]

def setup_classroom_block(instance_path: str, block_type: int):
    source_file = f"../base_classrooms/classrooms_{block_type}.json"
    target_file = os.path.join(instance_path, "classrooms.json")
    shutil.copy(source_file, target_file)

def main():
    SEEDS = list(range(1, 21))  # 20 instancias
    DIFFICULTIES = ["A+", "A-"]
    ALGORITHMS = ["GA", "SA"]
    CLASSROOM_BLOCKS = [24, 19]
    
    BASE_INSTANCES_DIR = "../generated_instances"
    RESULTS_FILE = "../anova_results_randomized.csv"

    # Generar la lista completa de todas las combinaciones de corridas
    all_runs = []
    for seed in SEEDS:
        for diff in DIFFICULTIES:
            for class_block in CLASSROOM_BLOCKS:
                for algo in ALGORITHMS:
                    all_runs.append({
                        "seed": seed,
                        "diff": diff,
                        "class_block": class_block,
                        "algo": algo
                    })

    # Aleatorizar el orden de las corridas para garantizar la independencia
    random.seed()
    random.shuffle(all_runs)

    total_runs = len(all_runs)
    print("="*60)
    print(f"Experimento Aleatorizado: {total_runs} corridas")
    print("El orden de ejecución ha sido mezclado aleatoriamente.")
    print("="*60)

    # Inicializar CSV con encabezados (añadiendo orden de ejecución y timestamp)
    file_exists = os.path.isfile(RESULTS_FILE)
    with open(RESULTS_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Execution_Order", "Timestamp", "Seed", "Difficulty", 
                "Classroom_Block", "Algorithm", "Fitness", 
                "Hard_Violations", "Soft_Penalty", "Execution_Time_Sec", "Status"
            ])

    # Ejecutar cada combinación en el orden aleatorio y registrar resultados inmediatamente
    for current_order, run in enumerate(all_runs, start=1):
        seed = run["seed"]
        diff = run["diff"]
        class_block = run["class_block"]
        algo = run["algo"]

        instance_path = os.path.join(BASE_INSTANCES_DIR, f"seed_{seed}", diff)
        
        # Obtener el momento exacto en el que inicia el tratamiento
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n[{current_order}/{total_runs}] {timestamp} -> Seed: {seed} | Diff: {diff} | Aulas: {class_block} | Algo: {algo}")

        if not os.path.exists(instance_path):
            print(f"  No se encontró la ruta {instance_path}. Guardando como omitido...")
            with open(RESULTS_FILE, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([current_order, timestamp, seed, diff, class_block, algo, "", "", "", "", "SKIPPED_NOT_FOUND"])
            continue

        # Preparar el archivo de aulas
        setup_classroom_block(instance_path, class_block)

        start_time = time.time()
        status = "SUCCESS"
        best_fitness = ""
        hard_viols = ""
        soft_penalty = ""

        try:
            # Inicializar y correr
            loader = DataLoader(instance_path)
            loader.load_all()

            if algo == "GA":
                schedules = run_genetic_algorithm(loader, population_size=200, generations=500, num_results=1, verbose=False)
            elif algo == "SA":
                schedules = run_simulated_annealing(loader, verbose=False)

            if schedules and len(schedules) > 0:
                best_schedule = schedules[0]
                best_fitness = round(best_schedule.fitness_val, 4)
                hard_viols = best_schedule.hard_violations
                soft_penalty = round(sum(best_schedule.soft_violations.values()), 4) if best_schedule.soft_violations else 0
            else:
                status = "FAILED_NO_SCHEDULE"

        except Exception as e:
            status = f"ERROR: {type(e).__name__}"
            print(f"  [!] Fallo en la ejecución: {e}")
            traceback.print_exc()

        # Registrar tiempo de CPU
        exec_time = round(time.time() - start_time, 2)
        print(f"  -> Resultado: Fitness={best_fitness}, Hard={hard_viols}, Tiempo={exec_time}s, Estado={status}")

        # Guardar inmediatamente con la información de orden y tiempo
        with open(RESULTS_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                current_order, timestamp, seed, diff, 
                class_block, algo, best_fitness, 
                hard_viols, soft_penalty, exec_time, status
            ])

    print("\n" + "="*60)
    print("Experimento completado. Todos los resultados han sido guardados.")
    print(f"Resultados en: {RESULTS_FILE}")
    print("="*60)

if __name__ == "__main__":
    main()