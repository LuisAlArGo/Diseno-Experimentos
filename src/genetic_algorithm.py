import random
import copy
import math
from typing import List, Tuple, Dict, Optional
from collections import defaultdict

from deap import base, creator, tools, algorithms

from DataLoader import DataLoader
from Schedule import Schedule, build_random_schedule, create_empty_schedule, DAY_PAIRS, DAY_WEIGHTS, _find_consecutive_blocks
from Group import Group
from HardRestrictions import HardRestrictions
from SoftRestrictions import SoftRestrictions
from BlockSchedule import BlockSchedule


class GeneticScheduler:
    """
    Planificador de horarios académicos utilizando algoritmos genéticos mediante la librería DEAP.
    
    Esta clase orquesta todo el proceso evolutivo: inicialización de la población,
    definición de funciones de fitness, operadores genéticos (cruce y mutación) y
    el ciclo principal de evolución.
    """
    
    def __init__(self, 
                 loader: DataLoader,
                 population_size: int = 100,
                 generations: int = 200,
                 cx_prob: float = 0.65,
                 mut_prob: float = 0.35,
                 tournament_size: int = 5,
                 elitism_size: int = 5,
                 hard_weight: float = 1000.0,
                 soft_weight: float = 100.0):
        """
        Inicializa el planificador genético con los parámetros de configuración.

        Args:
            loader (DataLoader): Objeto que contiene los datos cargados (cursos, profesores, aulas).
            population_size (int): Tamaño de la población en cada generación.
            generations (int): Número máximo de generaciones a ejecutar.
            cx_prob (float): Probabilidad de cruce (Crossover).
            mut_prob (float): Probabilidad de mutación.
            tournament_size (int): Tamaño del torneo para la selección de padres.
            elitism_size (int): Número de mejores individuos que pasan intactos a la siguiente generación.
            hard_weight (float): Penalización por cada violación de restricción dura.
            soft_weight (float): Penalización por cada violación de restricción blanda.
        """
        self.loader = loader
        self.population_size = population_size
        self.generations = generations
        self.cx_prob = cx_prob
        self.mut_prob = mut_prob
        self.tournament_size = tournament_size
        self.elitism_size = elitism_size
        self.hard_weight = hard_weight
        self.soft_weight = soft_weight
        
        # Inicialización de evaluadores de restricciones
        self.hard_eval = HardRestrictions()
        self.soft_eval = SoftRestrictions()
        
        self._precompute_data()
        self._setup_deap()
    
    def _precompute_data(self):
        """
        Precalcula y organiza estructuras de datos auxiliares para optimizar
        las búsquedas durante la mutación y generación de horarios.
        
        Organiza bloques de tiempo por día, profesores por curso y separa
        los tipos de aulas (laboratorios vs regulares).
        """
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
        
        self.labs = [r for r in self.loader.classrooms if r.type == "lab"]
        self.regular_rooms = [r for r in self.loader.classrooms if r.type != "lab"]
        
        self.all_days = list(DAY_WEIGHTS.keys())
        self.day_weights_values = list(DAY_WEIGHTS.values())
    
    def _setup_deap(self):
        """
        Configura el framework DEAP.
        
        Define:
        - FitnessMin: Objetivo de minimizar la penalización.
        - Individual: Basado en la clase Schedule.
        - Toolbox: Registra las funciones de evaluación, selección, cruce y mutación.
        """
        if hasattr(creator, "FitnessMin"):
            del creator.FitnessMin
        if hasattr(creator, "Individual"):
            del creator.Individual
        
        # Fitness negativo porque buscamos minimizar penalizaciones
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        creator.create("Individual", Schedule, fitness=creator.FitnessMin)
        
        self.toolbox = base.Toolbox()
        
        self.toolbox.register("individual", self._create_individual)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("evaluate", self._evaluate)
        self.toolbox.register("mate", self._crossover)
        self.toolbox.register("mutate", self._mutate)
        self.toolbox.register("select", tools.selTournament, tournsize=self.tournament_size)
    
    def _create_individual(self) -> Schedule:
        """
        Fábrica de individuos. Crea un horario aleatorio inicial.
        
        Returns:
            Schedule: Un objeto Schedule (Individuo de DEAP) con fitness calculado.
        """
        random_schedule = build_random_schedule(self.loader)
        
        ind = creator.Individual(class_groups=random_schedule.class_groups)
        ind.fitness = creator.FitnessMin()
        
        # Evaluamos inmediatamente para tener valores iniciales
        self._evaluate(ind)
        
        return ind

    def _clone_individual(self, individual: Schedule) -> Schedule:
        """
        Crea una copia profunda de un individuo.
        
        Es crucial en algoritmos genéticos para asegurar que modificar un hijo
        no afecte al padre si comparten referencias a objetos mutables (como Groups).
        """
        new_groups = {}
        for group_id, group in individual.class_groups.items():
            new_groups[group_id] = group.clone()
        
        new_ind = creator.Individual(class_groups=new_groups)
        new_ind.fitness = creator.FitnessMin()
        
        if individual.fitness.valid:
            new_ind.fitness.values = individual.fitness.values
            
        new_ind.hard_violations = individual.hard_violations
        new_ind.soft_violations = dict(individual.soft_violations)
        
        return new_ind
    
    def _evaluate(self, individual: Schedule) -> Tuple[float]:
        """
        Función de Fitness.
        
        Calcula la penalización total sumando:
        (Violaciones Duras * Peso Duro) + (Violaciones Blandas * Peso Blando).
        
        Args:
            individual (Schedule): El horario a evaluar.
            
        Returns:
            Tuple[float]: Una tupla con un solo valor (penalización total), requerido por DEAP.
        """
        groups = list(individual.class_groups.values())
        total_hard, hard_details = self.hard_eval.evaluate(groups)
        individual.hard_violations = total_hard
        
        soft_penalty, soft_details = self.soft_eval.evaluate(groups)
        individual.soft_violations = soft_details
        
        fitness_value = (total_hard * self.hard_weight) + (soft_penalty * self.soft_weight)
        individual.fitness_val = fitness_value
        return (fitness_value,)
    
    def _crossover(self, ind1: Schedule, ind2: Schedule) -> Tuple[Schedule, Schedule]:
        """
        Operador de Cruce (Crossover).
        
        Implementa un intercambio basado en semestres. Intercambia la configuración
        completa de todos los grupos de ciertos semestres entre dos padres.
        Esto preserva la coherencia interna de un semestre (que suele ser buena)
        mientras mezcla configuraciones.
        
        Args:
            ind1, ind2: Los dos individuos padres.
            
        Returns:
            Tuple[Schedule, Schedule]: Dos nuevos individuos hijos.
        """
        groups1_by_sem = defaultdict(list)
        groups2_by_sem = defaultdict(list)
        
        # Agrupar por semestre
        for group in ind1.class_groups.values():
            groups1_by_sem[group.course.semester].append(group)
        for group in ind2.class_groups.values():
            groups2_by_sem[group.course.semester].append(group)
        
        all_semesters = sorted(set(groups1_by_sem.keys()) & set(groups2_by_sem.keys()))
        if len(all_semesters) < 2:
            return ind1, ind2
        
        # Seleccionar semestres aleatorios para intercambiar
        num_to_swap = random.randint(1, len(all_semesters) // 2)
        semesters_to_swap = random.sample(all_semesters, num_to_swap)
        
        new_groups1 = {}
        new_groups2 = {}
        
        # Construir los hijos
        for semester in all_semesters:
            if semester in semesters_to_swap:
                # Intercambiar grupos de este semestre
                for group in groups2_by_sem[semester]:
                    cloned = group.clone()
                    new_groups1[cloned.get_id()] = cloned
                for group in groups1_by_sem[semester]:
                    cloned = group.clone()
                    new_groups2[cloned.get_id()] = cloned
            else:
                # Mantener grupos originales
                for group in groups1_by_sem[semester]:
                    cloned = group.clone()
                    new_groups1[cloned.get_id()] = cloned
                for group in groups2_by_sem[semester]:
                    cloned = group.clone()
                    new_groups2[cloned.get_id()] = cloned
        
        # Asegurar que no falten grupos (manejo de casos borde)
        for group_id in ind1.class_groups:
            if group_id not in new_groups1:
                new_groups1[group_id] = ind1.class_groups[group_id].clone()
        for group_id in ind2.class_groups:
            if group_id not in new_groups2:
                new_groups2[group_id] = ind2.class_groups[group_id].clone()
        
        offspring1 = creator.Individual(class_groups=new_groups1)
        offspring2 = creator.Individual(class_groups=new_groups2)
        
        offspring1.fitness = creator.FitnessMin()
        offspring2.fitness = creator.FitnessMin()
        
        return offspring1, offspring2
    
    def _mutate(self, individual: Schedule) -> Tuple[Schedule]:
        """
        Operador de Mutación.
        
        Selecciona aleatoriamente un tipo de mutación para aplicar a un individuo.
        Las probabilidades cambian dependiendo de si el individuo tiene violaciones
        duraso no.
        
        Tipos de mutación:
        - Profesor: Cambia el profesor asignado.
        - Aula (Classroom): Cambia el aula asignada.
        - Horario (Schedule): Mueve el grupo a otro bloque de tiempo.
        - Swap: Intercambia horarios entre dos grupos del mismo curso.
        """
        groups = list(individual.class_groups.values())
        if not groups:
            return (individual,)
        
        if individual.hard_violations > 0:
            # Si hay errores graves, hacer mas de horario, profesor o aula para explorar
            mutation_type = random.choices(
                ['professor', 'classroom', 'schedule', 'swap'],
                weights=[0.3, 0.3, 0.35, 0.05],
                k=1
            )[0]
        else:
            # Si es válido, swap es mejor en explotacion
            mutation_type = random.choices(
                ['professor', 'classroom', 'schedule', 'swap'],
                weights=[0.2, 0.2, 0.4, 0.2],
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
        
        return (individual,)
    
    def _mutate_professor(self, groups: List[Group]):
        """Asigna un nuevo profesor aleatorio válido para el curso del grupo seleccionado."""
        group = random.choice(groups)
        available_profs = self.professors_by_course.get(group.course.id, [])
        if available_profs and len(available_profs) > 1:
            new_prof = random.choice(available_profs)
            current_id = group.professor.id if group.professor else None
            # Intentar encontrar uno diferente al actual
            for _ in range(5):
                if new_prof.id != current_id:
                    break
                new_prof = random.choice(available_profs)
            group.professor = new_prof
    
    def _mutate_classroom(self, groups: List[Group]):
        """Asigna una nueva aula aleatoria respetando si requiere laboratorio o no."""
        group = random.choice(groups)
        if group.course.lab and self.labs:
            group.classroom = random.choice(self.labs)
        elif self.regular_rooms:
            group.classroom = random.choice(self.regular_rooms)
        else:
            group.classroom = random.choice(self.loader.classrooms)
    
    def _mutate_schedule(self, groups: List[Group]):
        """Mueve un grupo a un nuevo conjunto de bloques de tiempo aleatorios."""
        group = random.choice(groups)
        new_blocks = self._get_random_blocks(group.course)
        if new_blocks:
            group.schedules = new_blocks

    def _get_random_blocks(self, course) -> List[BlockSchedule]:
        """
        Genera una lista válida de bloques de tiempo aleatorios para un curso.
        Maneja la lógica de bloques consecutivos y división de días (ej. Lun/Jue).
        """
        schedules = []
        
        # Cursos cortos (<= 3 horas): Todo en un mismo día
        if course.hours <= 3:
            for _ in range(20): # Intentos
                day = random.choices(self.all_days, weights=self.day_weights_values, k=1)[0]
                day_blocks = self.blocks_by_day.get(day, [])
                if not day_blocks: continue
                
                start_index = random.randrange(len(day_blocks))
                found = _find_consecutive_blocks(day_blocks, start_index, course.hours)
                if found:
                    return found
        
        # Cursos largos: Dividir en dos días
        else:
            hours_day1 = math.ceil(course.hours / 2)
            hours_day2 = course.hours - hours_day1
            
            for _ in range(20):
                day1 = random.choices(self.all_days, weights=self.day_weights_values, k=1)[0]
                day2 = random.choice(DAY_PAIRS.get(day1, ["Lunes"]))
                day1_blocks = self.blocks_by_day.get(day1, [])
                day2_blocks = self.blocks_by_day.get(day2, [])
                
                if not day1_blocks or not day2_blocks: continue

                # Buscar bloque en Dia 1
                idx1 = random.randrange(len(day1_blocks))
                blocks1 = _find_consecutive_blocks(day1_blocks, idx1, hours_day1)
                
                if not blocks1: continue
                
                # Intentar alinear la hora en Dia 2
                h1 = blocks1[0].block.start_hour
                idx2 = -1
                for i, b in enumerate(day2_blocks):
                    if b.block.start_hour == h1:
                        idx2 = i
                        break
                
                if idx2 != -1:
                    blocks2 = _find_consecutive_blocks(day2_blocks, idx2, hours_day2)
                    if blocks2:
                        return blocks1 + blocks2
        
        return []
    
    def _mutate_swap(self, groups: List[Group]):
        """Intercambia los horarios entre dos grupos del mismo curso (ej. Grupo A y Grupo B)."""
        groups_by_course = defaultdict(list)
        for group in groups:
            groups_by_course[group.course.id].append(group)
        
        # Filtrar cursos que tienen múltiples grupos
        multi_group_courses = [cid for cid, glist in groups_by_course.items() if len(glist) > 1]
        if not multi_group_courses:
            return
            
        course_id = random.choice(multi_group_courses)
        course_groups = groups_by_course[course_id]
        if len(course_groups) >= 2:
            g1, g2 = random.sample(course_groups, 2)
            # Swap
            g1.schedules, g2.schedules = g2.schedules, g1.schedules
    
    def evolve(self, verbose: bool = True) -> Schedule:
        """
        Ejecuta el algoritmo genético completo.
        
        1. Genera población inicial.
        2. Itera por el número de generaciones.
        3. Aplica Elitismo, Selección, Cruce y Mutación.
        4. Reporta estadísticas.
        
        Returns:
            Schedule: El mejor horario encontrado al finalizar.
        """
        if verbose:
            print(f"Creando población inicial de {self.population_size} individuos")
        
        population = self.toolbox.population(n=self.population_size)
        # population = self._create_init_heur_pop(verbose=verbose)
        
        # Evaluación inicial
        fitnesses = list(map(self.toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit
        
        # Verificar si la primera genero un horario valido ---
        best_init = tools.selBest(population, 1)[0]
        if best_init.hard_violations == 0:
            if verbose:
                self._print_stats(population, 0)
                print("\n Solución válida encontrada")
            return best_init

        if verbose:
            self._print_stats(population, 0)
        
        # Bucle generacional
        for gen in range(1, self.generations + 1):
            # 1. Elitismo: Guardar los mejores
            elite = tools.selBest(population, self.elitism_size)
            
            # 2. Selección para reproducción
            offspring = self.toolbox.select(population, len(population) - self.elitism_size)
            offspring = list(map(lambda x: self._clone_individual(x), offspring))
            
            # 3. Cruce (Mate)
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < self.cx_prob:
                    self.toolbox.mate(child1, child2)
                    # Invalidar fitness tras modificación
                    del child1.fitness.values
                    del child2.fitness.values
            
            # 4. Mutación
            for mutant in offspring:
                if random.random() < self.mut_prob:
                    self.toolbox.mutate(mutant)
                    del mutant.fitness.values
            
            # 5. Re-evaluación de individuos modificados
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = map(self.toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
            
            # 6. Nueva población = Élite + Descendencia
            population[:] = elite + offspring
            
            best_in_gen = tools.selBest(population, 1)[0]
            
            # Verificar si es un horario valido
            if best_in_gen.hard_violations == 0:
                if verbose:
                    self._print_stats(population, gen)
                    print("\n" + "="*80)
                    print(f"Solución válida encontrada en la generación {gen}")
                    print("="*80)
                    self._print_individual_details(best_in_gen)
                return best_in_gen

            if verbose and (gen % 10 == 0):
                self._print_stats(population, gen)
        
        # Selección del mejor global
        best = tools.selBest(population, 1)[0]
        if verbose:
            print("\n" + "="*80)
            print("EVOLUCIÓN COMPLETADA")
            print("="*80)
            self._print_individual_details(best)
        
        return best
    
    def _print_stats(self, population, generation):
        """Imprime estadísticas básicas de la generación actual."""
        fitnesses = [ind.fitness.values[0] for ind in population]
        hard_viols = [ind.hard_violations for ind in population]
        print(f"\n--- Generación {generation} ---")
        print(f"Fitness - Min: {min(fitnesses):.2f}, Avg: {sum(fitnesses)/len(fitnesses):.2f}, Max: {max(fitnesses):.2f}")
        print(f"Violaciones Duras - Min: {min(hard_viols)}, Avg: {sum(hard_viols)/len(hard_viols):.2f}, Max: {max(hard_viols)}")
        valid_schedules = sum(1 for ind in population if ind.hard_violations == 0)
        print(f"Horarios Válidos: {valid_schedules}/{len(population)} ({100*valid_schedules/len(population):.1f}%)")
    
    def _print_individual_details(self, individual: Schedule):
        """Imprime detalles detallados del mejor individuo encontrado."""
        print(f"\nMejor Fitness: {individual.fitness.values[0]:.2f}")
        print(f"Violaciones Duras: {individual.hard_violations}")
        print(f"Es Válido: {'SÍ' if individual.is_valid() else '✗ NO'}")
        if individual.soft_violations:
            print("\nViolaciones Blandas:")
            for key, value in individual.soft_violations.items():
                print(f"  - {key}: {value:.4f}")
        print(f"\nTotal de Grupos: {len(individual.class_groups)}")

    def _create_init_heur_pop(self, verbose: bool=False) -> List[Schedule]:
        population =[]
        from Heuristic import heuristic_schedule
        heuristic_ratio = 0.2
        heuristic_count = int(self.population_size * heuristic_ratio)
        if verbose:
            print(f"\nGenerating {heuristic_count} heuristic schedules...")

        for i in range(heuristic_count):
            try:
                if verbose:
                    print(f"    Heuristic schedule {i+1}/{heuristic_count}...", end=" ")
                
                heuristic_sched = heuristic_schedule(
                    self.loader,
                    hard_weight=self.hard_weight,
                    soft_weight=self.soft_weight,
                    max_backtracks=500,
                    verbose=False
                )
                
                individual = creator.Individual(class_groups=heuristic_sched.class_groups)
                individual.fitness = creator.FitnessMin()

                if hasattr(heuristic_sched, 'hard_violations'):
                    individual.hard_violations = heuristic_sched.hard_violations
                if hasattr(heuristic_sched, 'soft_violations'):
                    individual.soft_violations = heuristic_sched.soft_violations
                if hasattr(heuristic_sched, 'fitness_val'):
                    individual.fitness.values = (heuristic_sched.fitness_val,)
                else:
                    self._evaluate(individual)
                
                population.append(individual)

                if verbose:
                    status = "VALID" if individual.hard_violations == 0 else f"INVALID: {individual.hard_violations} violations"
                    print(status)
            except Exception as e:
                if verbose:
                    print(f"Failed: {str(e)}")
                population.append(self._create_individual())

        if verbose:
            valid_count = sum(1 for individual in population if individual.hard_violations == 0)
            print(f"\nHeuristic results: {valid_count}/{heuristic_count} valid schedules generated")
            
        remaining = self.population_size - len(population)
        if remaining > 0:
            if verbose:
                print(f"\nGenerating {remaining} random schedules...")
            for _ in range(remaining):
                population.append(self._create_individual())
        return population

def run_genetic_algorithm(loader: DataLoader, 
                          population_size: int = 100,
                          generations: int = 200,
                          verbose: bool = True) -> Schedule:
    """
    Función de ayuda (Helper) para instanciar y ejecutar el planificador genético.
    
    Args:
        loader (DataLoader): Datos de entrada.
        population_size (int): Tamaño de la población.
        generations (int): Número de generaciones.
        verbose (bool): Si es True, imprime logs en consola.
        
    Returns:
        Schedule: El mejor horario generado.
    """
    scheduler = GeneticScheduler(
        loader=loader,
        population_size=population_size,
        generations=generations,
        cx_prob=0.7,
        mut_prob=0.3,
        tournament_size=5,
        elitism_size=max(5, population_size // 20)
    )
    best_schedule = scheduler.evolve(verbose=verbose)
    return best_schedule