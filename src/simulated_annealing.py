import random
import math
import copy
from typing import List
from collections import defaultdict

from DataLoader import DataLoader
from Schedule import Schedule, build_random_schedule, DAY_PAIRS, DAY_WEIGHTS, _find_consecutive_blocks
from Group import Group
from BlockSchedule import BlockSchedule
from HardRestrictions import HardRestrictions
from SoftRestrictions import SoftRestrictions


class SimulatedAnnealingScheduler:
    """
    Planificador de horarios académicos usando Recocido Simulado (Simulated Annealing).

    El algoritmo parte de una solución aleatoria y la mejora iterativamente aceptando
    soluciones vecinas. Soluciones peores se aceptan con probabilidad exp(-Δ/T),
    donde T es la temperatura actual (decrece con el tiempo).
    """

    def __init__(self,
                 loader: DataLoader,
                 initial_temp: float = 50000.0,
                 cooling_rate: float = 0.995,
                 min_temp: float = 0.1,
                 iterations_per_temp: int = 50,
                 hard_weight: float = 1000.0,
                 soft_weight: float = 100.0):
        """
        Args:
            loader: Datos cargados (cursos, profesores, aulas).
            initial_temp: Temperatura inicial. Controla cuánto se acepta al principio.
            cooling_rate: Factor de enfriamiento por paso (típicamente 0.99-0.999).
            min_temp: Temperatura mínima para detener el algoritmo.
            iterations_per_temp: Iteraciones (vecinos evaluados) por nivel de temperatura.
            hard_weight: Penalización por cada violación dura.
            soft_weight: Penalización por cada violación blanda.
        """
        self.loader = loader
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.iterations_per_temp = iterations_per_temp
        self.hard_weight = hard_weight
        self.soft_weight = soft_weight

        self.hard_eval = HardRestrictions()
        self.soft_eval = SoftRestrictions()

        self._precompute_data()

    def _precompute_data(self):
        self.blocks_by_day = {}
        for block in self.loader.time_blocks:
            self.blocks_by_day.setdefault(block.day, []).append(block)
        for day in self.blocks_by_day:
            self.blocks_by_day[day].sort(key=lambda b: b.block.start_hour)

        self.professors_by_course = {}
        for course in self.loader.courses:
            self.professors_by_course[course.id] = [
                p for p in self.loader.professors if course.id in p.courses
            ]

        self.labs = [r for r in self.loader.classrooms if r.type.lower() == "lab"]
        self.regular_rooms = [r for r in self.loader.classrooms if r.type.lower() != "lab"]

        self.all_days = list(DAY_WEIGHTS.keys())
        self.day_weights_values = list(DAY_WEIGHTS.values())

    # ------------------------------------------------------------------
    # Evaluación
    # ------------------------------------------------------------------

    def _evaluate(self, schedule: Schedule) -> float:
        groups = list(schedule.class_groups.values())
        total_hard, _ = self.hard_eval.evaluate(groups)
        soft_penalty, soft_details = self.soft_eval.evaluate(groups)

        schedule.hard_violations = total_hard
        schedule.soft_violations = soft_details
        fitness = total_hard * self.hard_weight + soft_penalty * self.soft_weight
        schedule.fitness_val = fitness
        return fitness

    # ------------------------------------------------------------------
    # Generación de vecino
    # ------------------------------------------------------------------

    def _get_neighbor(self, schedule: Schedule) -> Schedule:
        """Genera un vecino clonando el horario y aplicando una mutación."""
        neighbor = self._clone_schedule(schedule)
        groups = list(neighbor.class_groups.values())

        if schedule.hard_violations > 0:
            mutation_type = random.choices(
                ['professor', 'classroom', 'schedule', 'swap'],
                weights=[0.3, 0.3, 0.35, 0.05],
                k=1
            )[0]
        else:
            mutation_type = random.choices(
                ['professor', 'classroom', 'schedule', 'swap'],
                weights=[0.15, 0.15, 0.5, 0.2],
                k=1
            )[0]

        if mutation_type == 'professor':
            self._mutate_professor(groups)
        elif mutation_type == 'classroom':
            self._mutate_classroom(groups)
        elif mutation_type == 'schedule':
            self._mutate_schedule(groups)
        elif mutation_type == 'swap':
            self._mutate_swap(groups)

        return neighbor

    def _clone_schedule(self, schedule: Schedule) -> Schedule:
        new_groups = {gid: g.clone() for gid, g in schedule.class_groups.items()}
        clone = Schedule(class_groups=new_groups)
        clone.hard_violations = schedule.hard_violations
        clone.soft_violations = dict(schedule.soft_violations)
        clone.fitness_val = schedule.fitness_val
        return clone

    # ------------------------------------------------------------------
    # Operadores de mutación (reutilizados del AG)
    # ------------------------------------------------------------------

    def _mutate_professor(self, groups: List[Group]):
        group = random.choice(groups)
        available = self.professors_by_course.get(group.course.id, [])
        if len(available) > 1:
            current_id = group.professor.id if group.professor else None
            for _ in range(5):
                new_prof = random.choice(available)
                if new_prof.id != current_id:
                    break
            group.professor = new_prof

    def _mutate_classroom(self, groups: List[Group]):
        group = random.choice(groups)
        if group.course.lab and self.labs:
            group.classroom = random.choice(self.labs)
        elif self.regular_rooms:
            group.classroom = random.choice(self.regular_rooms)
        else:
            group.classroom = random.choice(self.loader.classrooms)

    def _mutate_schedule(self, groups: List[Group]):
        group = random.choice(groups)
        new_blocks = self._get_random_blocks(group.course)
        if new_blocks:
            group.schedules = new_blocks

    def _mutate_swap(self, groups: List[Group]):
        groups_by_course = defaultdict(list)
        for g in groups:
            groups_by_course[g.course.id].append(g)
        multi = [cid for cid, gl in groups_by_course.items() if len(gl) > 1]
        if not multi:
            return
        cid = random.choice(multi)
        g1, g2 = random.sample(groups_by_course[cid], 2)
        g1.schedules, g2.schedules = g2.schedules, g1.schedules

    def _get_random_blocks(self, course) -> List[BlockSchedule]:
        if course.hours <= 3:
            for _ in range(20):
                day = random.choices(self.all_days, weights=self.day_weights_values, k=1)[0]
                day_blocks = self.blocks_by_day.get(day, [])
                if not day_blocks:
                    continue
                idx = random.randrange(len(day_blocks))
                found = _find_consecutive_blocks(day_blocks, idx, course.hours)
                if found:
                    return found
        else:
            hours_d1 = math.ceil(course.hours / 2)
            hours_d2 = course.hours - hours_d1
            for _ in range(20):
                day1 = random.choices(self.all_days, weights=self.day_weights_values, k=1)[0]
                day2 = random.choice(DAY_PAIRS.get(day1, ["Lunes"]))
                d1_blocks = self.blocks_by_day.get(day1, [])
                d2_blocks = self.blocks_by_day.get(day2, [])
                if not d1_blocks or not d2_blocks:
                    continue
                idx1 = random.randrange(len(d1_blocks))
                blocks1 = _find_consecutive_blocks(d1_blocks, idx1, hours_d1)
                if not blocks1:
                    continue
                alignment = random.choice(["same_start", "same_end"])
                sh1 = blocks1[0].block.start_hour
                target = sh1 if alignment == "same_start" else sh1 + hours_d1 - hours_d2
                idx2 = next((i for i, b in enumerate(d2_blocks) if b.block.start_hour == target), -1)
                if idx2 != -1:
                    blocks2 = _find_consecutive_blocks(d2_blocks, idx2, hours_d2)
                    if blocks2:
                        return blocks1 + blocks2
        return []

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def anneal(self, verbose: bool = True) -> Schedule:
        """
        Ejecuta el recocido simulado y devuelve el mejor horario encontrado.
        """
        current = build_random_schedule(self.loader)
        current_fitness = self._evaluate(current)

        best = self._clone_schedule(current)
        best_fitness = current_fitness

        temp = self.initial_temp
        iteration = 0

        if verbose:
            total_iters = int(math.log(self.min_temp / self.initial_temp) /
                              math.log(self.cooling_rate)) * self.iterations_per_temp
            print(f"Temperatura inicial: {temp:.1f} | Enfriamiento: {self.cooling_rate} | "
                  f"Iteraciones totales aprox.: {total_iters:,}")

        while temp > self.min_temp:
            for _ in range(self.iterations_per_temp):
                neighbor = self._get_neighbor(current)
                neighbor_fitness = self._evaluate(neighbor)

                delta = neighbor_fitness - current_fitness

                # Aceptar si mejora, o con probabilidad exp(-Δ/T) si empeora
                if delta < 0 or random.random() < math.exp(-delta / temp):
                    current = neighbor
                    current_fitness = neighbor_fitness

                    if current_fitness < best_fitness:
                        best = self._clone_schedule(current)
                        best_fitness = current_fitness

            temp *= self.cooling_rate
            iteration += 1

            if verbose and iteration % 200 == 0:
                print(f"  Temp: {temp:8.2f} | Fitness actual: {current_fitness:10.2f} | "
                      f"Mejor: {best_fitness:10.2f} | "
                      f"Hard: {best.hard_violations} | "
                      f"Válido: {'Sí' if best.hard_violations == 0 else 'No'}")

        if verbose:
            print(f"\nRecocido finalizado.")
            print(f"Mejor fitness: {best_fitness:.2f}")
            print(f"Violaciones duras: {best.hard_violations}")
            print(f"Válido: {'SÍ' if best.hard_violations == 0 else 'NO'}")

        return best


def run_simulated_annealing(loader: DataLoader,
                            initial_temp: float = 50000.0,
                            cooling_rate: float = 0.995,
                            min_temp: float = 0.1,
                            iterations_per_temp: int = 50,
                            verbose: bool = True) -> List[Schedule]:
    """
    Helper para instanciar y correr el SA. Devuelve una lista con el mejor horario
    (misma interfaz que run_genetic_algorithm para compatibilidad con ExperimentRunner).
    """
    scheduler = SimulatedAnnealingScheduler(
        loader=loader,
        initial_temp=initial_temp,
        cooling_rate=cooling_rate,
        min_temp=min_temp,
        iterations_per_temp=iterations_per_temp,
    )
    best = scheduler.anneal(verbose=verbose)
    return [best]
