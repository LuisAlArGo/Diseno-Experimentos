from typing import List, Dict, Tuple
from collections import defaultdict
from Group import Group
from BlockSchedule import BlockSchedule
from Professor import Professor
from Schedule import Schedule

class SoftRestrictions:
    def __init__(self,
                combination_weight: float = 1.0,
                balance_weight: float = 0.5,
                professor_gap_weight: float = 0.3,
                student_gap_weight: float = 0.2,
                professor_preference_weight: float = 0.4,
                classroom_adequacy_weight: float = 0.5,
                max_count_limit: int = 100000):
        # Asignación de los pesos que modularán el impacto de cada penalización.
        self.combination_weight = combination_weight
        self.balance_weight = balance_weight
        self.professor_gap_weight = professor_gap_weight
        self.student_gap_weight = student_gap_weight
        self.professor_preference_weight = professor_preference_weight
        self.classroom_adequacy_weight = classroom_adequacy_weight
        self.max_count_limit = max_count_limit

    def evaluate(self, groups: List[Group]) -> Tuple[float, Dict[str, float]]:
        """Evaluate soft restrictions for a schedule represented by `groups`.

        Current soft restriction: penalize semesters with fewer valid student
        course-group combinations. The penalty for a semester is computed as
        `weight * (1.0 / count)` when `count > 0`, or `weight * 10.0` when
        `count == 0` (strong penalty for zero valid combinations).

        Returns:
            Tuple[float, Dict[str, float]]: total penalty and a dict with
            per-semester combination counts and penalties.
        """
        # Diccionario para almacenar el desglose de las penalizaciones por categoría.
        details: Dict[str, float] = {}

        # Calcular la penalización para cada tipo de restricción suave.
        combination_penalty = self._evaluate_combinations(groups)
        details['combinations'] = combination_penalty

        balance_penalty = self._evaluate_class_balance(groups)
        details['class_balance'] = balance_penalty

        professor_gap_penalty = self._evaluate_professor_gaps(groups)
        details['professor_gaps'] = professor_gap_penalty

        student_gap_penalty = self._evaluate_student_gaps(groups)
        details['student_gaps'] = student_gap_penalty

        professor_preference_penalty = self._evaluate_professor_preferences(groups)
        details['professor_preferences'] = professor_preference_penalty

        classroom_adequacy_penalty = self._evaluate_classroom_adequacy(groups)
        details['clasroom_adequacy'] = classroom_adequacy_penalty

        # Sumar todas las penalizaciones para obtener el costo total (puntaje) del horario.
        total_penalty = (combination_penalty + balance_penalty +
                          professor_gap_penalty + student_gap_penalty +
                          professor_preference_penalty + classroom_adequacy_penalty)
        return total_penalty, details

    # ==============================================================================================

    def _evaluate_combinations(self, groups: List[Group]) -> float:
        """
        Penalize semesters with fewer valid course-group combinations.
        More combinations = more flexibility for students = better schedule.
        
        Args:
            groups (List[Group]): list of class groups in the schedule
        
        Returns:
            float: total combination penalty across all semesters
        """
        # Agrupar los grupos por semestre para analizarlos por separado.
        semester_schedule = defaultdict(list)
        for group in groups:
            if not group.schedules:
                continue
            for block in group.schedules:
                semester_schedule[group.course.semester].append((group, block))

        total_penalty = 0.0

        # Iterar sobre cada semestre para evaluar sus combinaciones.
        for semester, schedule in semester_schedule.items():
            # Contar cuántas formas válidas tiene un estudiante de tomar todas sus materias.
            count = self._count_valid_combinations(schedule, limit=self.max_count_limit)

            # La penalización es inversamente proporcional al número de combinaciones.
            if count <= 0:
                # Penalización alta si no hay ninguna combinación válida, lo que es un problema grave.
                penalty = self.combination_weight * 10.0
            else:
                # Penalización menor a medida que aumentan las combinaciones. 1/count disminuye a medida que count crece.
                penalty = self.combination_weight * (1.0 / float(count))
            total_penalty += penalty

        return total_penalty

    # ==============================================================================================

    def _count_valid_combinations(self, schedule: List[Tuple[Group, BlockSchedule]], limit: int = 100000) -> int:
        """Count the number of valid combinations (one group per course) for a semester.

        Uses backtracking to enumerate combinations where selected blocks do not
        conflict. Enumeration is capped at `limit` to avoid exponential blow-up.

        Returns:
            int: number of valid combinations found (capped at `limit`).
        """
        if not schedule:
            return 0

        # Organizar los grupos por materia ya que elegiremos un grupo por cada materia.
        course_groups = defaultdict(dict)
        for group, _ in schedule:
            course_groups[group.course.id][group.get_id()] = group

        course_groups_list = [list(groups.values()) for groups in course_groups.values()]
        
        if not course_groups_list:
            return 0
        count = 0

        def backtrack(idx: int, used_blocks: List[BlockSchedule]):
            nonlocal count
            if count >= limit:
                return
            # Caso base: se ha elegido un grupo para cada materia.
            if idx == len(course_groups_list): 
                count += 1
                return

            # Grupos disponibles para la materia actual.
            available_groups = course_groups_list[idx]

            for group in available_groups:
                # Si el grupo no choca con los ya seleccionados, se prueba esta rama.
                if self._group_conflicts_with_blocks(group, used_blocks):
                    continue

                backtrack(idx + 1, used_blocks + group.schedules)
                # Revisar el limite de nuevo
                if count >= limit:
                    return

        backtrack(0, [])
        return count
    # ==============================================================================================

    def _evaluate_class_balance(self, groups: List[Group]) -> float:
        """
        Penalize unbalanced group sizes for courses with multiple groups.
        For each course with multiple groups, calculate standard deviation of valid
        student combinations per group. Higher deviation = worse balance.

        The penalty encourages groups of the same course to have similar numbers
        of possible student combinations.
        
        Args:
            groups(List[Group]): list of class groups in the schedule

        Returns:
            float: total class balance penalty across all courses
        """
        # Agrupar los grupos por curso.
        course_groups = defaultdict(list)
        for group in groups:
            course_groups[group.course.id].append(group)
        total_penalty = 0.0

        for course_id, course_group_list in course_groups.items():
            if len(course_group_list) <= 1:
                continue

            group_counts = []
            # Para cada grupo de un mismo curso, se calcula un puntaje de "disponibilidad".
            for group in course_group_list:
                if not group.schedules:
                    group_counts.append(0)
                    continue
                
                conflicts = 0 
                # Se cuenta con cuántas otras materias del mismo semestre choca este grupo.
                for other_group in groups:
                    if other_group.course.id == group.course.id: continue
                    if other_group.course.semester != group.course.semester: continue
                    if self._groups_conflict(group, other_group):
                        conflicts += 1    
                # El puntaje de disponibilidad es inversamente proporcional al número de conflictos.
                availability = max(1, 100 - conflicts * 10)
                group_counts.append(availability)

            if len(group_counts) == 0 or sum(group_counts) == 0:
                continue

            # Se calcula el coeficiente de variación (CV) de los puntajes de disponibilidad.
            # Un CV alto indica un gran desbalance, lo cual es penalizado.
            mean = sum(group_counts) / len(group_counts)
            variance = sum((x - mean) ** 2 for x in group_counts) / len(group_counts)
            std_dev = variance ** 0.5

            if mean > 0:
                cv = std_dev / mean # El Coeficiente de Variación normaliza la desviación estándar.
                penalty = self.balance_weight * cv
                total_penalty += penalty

        return total_penalty

    # ==============================================================================================

    def _groups_conflict(self, group1: Group, group2: Group) -> bool:
        """
        Verifica si dos grupos tienen algún conflicto de horario.
        
        Returns:
            bool: True si hay conflicto, False en caso contrario.
        """
        if not group1.schedules or not group2.schedules:
            return False
        
        # Compara cada bloque de horario del grupo 1 con cada bloque del grupo 2.
        for block1 in group1.schedules:
            for block2 in group2.schedules:
                # Hay conflicto si coinciden en el día y sus bloques de tiempo se solapan.
                if block1.day == block2.day and block1.block.conflict(block2.block):
                    return True
        return False

    # ==============================================================================================

    def _evaluate_professor_gaps(self, groups: List[Group]) -> float:
        """
        Penalize gaps in professors' daily schedules. For each professor, on their teaching days:
        - Find their first and last class
        - Calculate total teaching hours
        - Penalty = (span - teaching_hours) * weight
        
        Args:
            groups(List[Group]): list of class groups in the schedule
        
        Returns:
            float: total professor gap penalty across all professors
        """
        # Agrupar todos los bloques de clase por profesor.
        professor_schedules = defaultdict(list)
        for group in groups:
            if not group.professor or not group.schedules: continue
            for block in group.schedules:
                professor_schedules[group.professor.id].append(block)

        total_penalty = 0.0

        for professor_id, blocks in professor_schedules.items():
            # Para cada profesor, agrupar sus clases por día.
            blocks_by_day = defaultdict(list)
            for block in blocks:
                blocks_by_day[block.day].append(block)

            # Analizar los huecos para cada día.
            for day, day_blocks in blocks_by_day.items():
                if len(day_blocks) <= 1: continue # No hay huecos si hay 0 o 1 clase.

                start_hours = [b.block.start_hour for b in day_blocks]
                end_hours = [b.block.end_hour for b in day_blocks]

                # Calcular el tiempo total que el profesor pasa en el campus ese día.
                earliest_start = min(start_hours)
                latest_end = max(end_hours)
                time_span = latest_end - earliest_start
                teaching_hours = len(day_blocks)
                gap_hours = time_span - teaching_hours
                
                if gap_hours > 0:
                    penalty = self.professor_gap_weight * gap_hours
                    total_penalty += penalty

        return total_penalty

    # ==============================================================================================

    def _evaluate_student_gaps(self, groups: List[Group]) -> float:
        """
        Penalize gaps in students' daily schedules. For each semester:
        - Find all possible valid course combinations
        - For each combination, calculate the daily gaps
        - Penalize based on average gap across all combinations
        
        Args:
            groups(List[Group]): list of class groups in the schedule
        
        Returns:
            float: total student gap penalty across all semesters
        """
        # Agrupar los grupos por semestre.
        semester_groups = defaultdict(list)
        for group in groups:
            if not group.schedules: continue
            semester_groups[group.course.semester].append(group)

        total_penalty = 0.0

        for semester, sem_groups in semester_groups.items():
            if len(sem_groups) <= 1: continue

            semester_schedule = []
            for group in sem_groups:
                for block in group.schedules:
                    semester_schedule.append((group, block))

            valid_combination_gaps = self._calculate_combination_gaps(semester_schedule)
            if len(valid_combination_gaps) > 0:
                # La penalización se basa en el promedio de huecos de todas las combinaciones posibles.
                avg_gap = sum(valid_combination_gaps) / len(valid_combination_gaps)
                penalty = self.student_gap_weight * avg_gap
                total_penalty += penalty

        return total_penalty

    # ==============================================================================================

    def _calculate_combination_gaps(self, schedule: List[Tuple[Group, BlockSchedule]], limit: int = 1000) -> List[float]:
        """
        Calculate gaps for all valid combinations in a semester.
        
        Args:
            schedule: list of (group, block) tuples for a semester
            limit: maximum number of combinations to evaluate; avoids running for too long

        Returns:
            list of gap hours for each valid combination
        """
        if not schedule: return []

        # Organizar grupos por curso
        course_groups = defaultdict(dict)
        for group, _ in schedule:
            course_groups[group.course.id][group.get_id()] = group
        courses = [list(groups.values()) for groups in course_groups.values()]
        
        if not courses: return []

        combination_gaps = []

        # Encontrar combinaciones y calcular sus huecos.
        def backtrack(index: int, selected_blocks: List[BlockSchedule]):
            if len(combination_gaps) >= limit: return # Parada temprana.
            
            # Caso base: se ha formado una combinación completa.
            if index == len(courses):
                gap = self._calculate_daily_gaps(selected_blocks)
                combination_gaps.append(gap)
                return

            available_groups = courses[index]
            for group in available_groups:
                if self._group_conflicts_with_blocks(group, selected_blocks): continue
                # Llamada recursiva con la nueva selección.
                backtrack(index + 1, selected_blocks + group.schedules)
                if len(combination_gaps) >= limit: return

        backtrack(0, [])
        return combination_gaps

    def _group_conflicts_with_blocks(self, group: Group, used_blocks: List[BlockSchedule]) -> bool:
        """Verifica si alguno de los bloques del grupo choca con los bloques ya agendados."""
        if not group.schedules:
            return False
            
        for g_block in group.schedules:
            for u_block in used_blocks:
                if g_block.day == u_block.day and g_block.block.conflict(u_block.block):
                    return True
        return False

    # ==============================================================================================

    def _calculate_daily_gaps(self, blocks: List[BlockSchedule]) -> float:
        """
        Calculates total gap hours across all days for a set of blocks.
        
        Args:
            blocks: list of BlockSchedule objects

        Returns:
            total gap hours across all days
        """
        if len(blocks) <= 1: return 0.0

        blocks_by_day = defaultdict(list)
        for block in blocks:
            blocks_by_day[block.day].append(block)

        total_gaps = 0.0
        for day, day_blocks in blocks_by_day.items():
            if len(day_blocks) <= 1: continue

            start_hours = [b.block.start_hour for b in day_blocks]
            end_hours = [b.block.end_hour for b in day_blocks]

            earliest_start = min(start_hours)
            latest_end = max(end_hours)
            time_span = latest_end - earliest_start
            class_hours = len(day_blocks)
            gap_hours = time_span - class_hours

            if gap_hours > 0:
                total_gaps += gap_hours

        return total_gaps

    # ==============================================================================================

    def _evaluate_professor_preferences(self, groups: List[Group]) -> float:
        """
        Penalize when professors don't get their preferred courses or schedules.
        Lower penalty = better match with preferences. For each professor:
        - Check if assigned courses match their preferred courses
        - Check if assigned time slots match their preferred schedules
        
        Args:
            groups(List[Group]): list of class groups in the schedule

        Returns:
            float: total preference mismatch penalty
        """
        # group assignments per professor
        professor_assignments = defaultdict(lambda: {'courses': set(), 'blocks': [], 'professor': None})
        for group in groups:
            if not group.professor: continue
            professor_id = group.professor.id
            professor_assignments[professor_id]['courses'].add(group.course)
            professor_assignments[professor_id]['professor'] = group.professor
            if group.schedules:
                professor_assignments[professor_id]['blocks'].extend(group.schedules)

        total_penalty = 0.0

        for professor_id, assignment in professor_assignments.items():
            professor = assignment['professor']
            assigned_courses = assignment['courses']
            assigned_blocks = assignment['blocks']
            
            # Penalización por cursos no preferidos.
            preferred_courses = set(professor.course_preferences)
            if len(preferred_courses) > 0 and len(assigned_courses) > 0:
                matched_courses = assigned_courses.intersection(preferred_courses)
                mismatch_ratio = 1.0 - (len(matched_courses) / len(assigned_courses))
                course_penalty = self.professor_preference_weight * mismatch_ratio
                total_penalty += course_penalty

            # Penalización por horarios no preferidos.
            if len(assigned_blocks) > 0 and len(professor.schedule_preferences) > 0:
                matched_blocks = 0
                for block in assigned_blocks:
                    if professor.prefers_schedule(block):
                        matched_blocks += 1
                # Calcular qué proporción de los horarios asignados no eran preferidos.
                schedule_mismatch = 1.0 - (matched_blocks / len(assigned_blocks))
                schedule_penalty = self.professor_preference_weight * schedule_mismatch
                total_penalty += schedule_penalty

        return total_penalty
    
    # ==============================================================================================

    def _evaluate_classroom_adequacy(self, groups: List[Group]) -> float:
        """
        Penalize inadequate classroom assignments:
        - Lab courses should be assigned to lab classrooms
        - Non-lab courses should not be assigned to lab classrooms
        - Groups without classroom recieve a strong penalty
        
        Args:
            groups(List[Group]): list of class groups in the schedule

        Returns:
            float: total classroom adequacy penalty
        """
        total_penalty = 0.0

        for group in groups:
            if group.classroom is None:
                total_penalty += self.classroom_adequacy_weight * 5.0
                continue

            is_lab_course = group.course.lab
            is_lab_classroom = 'lab' in group.classroom.type.lower()

            # Curso de laboratorio en un aula que no es de laboratorio.
            if is_lab_course and not is_lab_classroom:
                # Penalización alta, ya que el curso no se puede impartir correctamente.
                total_penalty += self.classroom_adequacy_weight * 3.0
            # Curso teórico en un aula de laboratorio.
            elif not is_lab_course and is_lab_classroom:
                # Penalización menor, ya que es un uso ineficiente de un recurso especializado.
                total_penalty += self.classroom_adequacy_weight * 1.5

        return total_penalty