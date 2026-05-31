from typing import Dict, List, Tuple
from collections import defaultdict
from Group import Group
from BlockSchedule import BlockSchedule

from util import *
from Professor import Professor

class HardRestrictions:
    def __init__(self):
        pass
    
    def evaluate(self, groups: List[Group]) -> Tuple[int, Dict[str, int]]:
        """
        Evaluate hard restrictions for a schedule represented by 'groups'.
        Restrictions checked:
            - No time conflicts for professors
            - No time conflicts for classrooms
            - No curriculum conflicts (students can attend all courses in their semester)
            - Professors do not exceed their maximum number of groups
            - Professors are scheduled within their working hours
        
        Args:
            groups (List[Group]): list of class groups in the schedule
        
        Returns:
            Tuple[int, Dict[str, int]]: total number of hard violations and a dict with
                details of each type of violation
        """

        # Diccionario para almacenar la cantidad de cada tipo de violación.
        violations = {
            'professor_conflict': 0,
            'classroom_conflict': 0,
            'curriculum_conflict': 0,
            'professor_overload': 0,
            'professor_unavailable': 0
        }
        
        professor_schedule = defaultdict(list) 
        classroom_schedule = defaultdict(list)  
        semester_schedule = defaultdict(list)   
        groups_by_professor: Dict[Professor, List[Group]] = defaultdict(list)
        
        # Organizar los grupos en las estructuras de datos 
        for group in groups:
            # Ignorar grupos que no están completamente asignados
            if not group.professor or not group.classroom or not group.schedules:
                continue
            
            # Agrupar por profesor para verificar sobrecarga y disponibilidad.
            groups_by_professor[group.professor].append(group)
            
            # Agrupar por semestre para verificar conflictos de currículo.
            semester_schedule[group.course.semester].append(group)

            # Poblar los horarios de profesores y aulas con cada bloque de horario del grupo.
            for block in group.schedules:
                professor_schedule[group.professor.id].append((group, block))
                classroom_schedule[group.classroom.number].append((group, block))
        
        
        # Calcular conflictos de horario para profesores.
        for prof_id, schedule in professor_schedule.items():
            violations['professor_conflict'] += self._time_conflicts(schedule)

        # Calcular conflictos de horario para aulas.
        for room_num, schedule in classroom_schedule.items():
            violations['classroom_conflict'] += self._time_conflicts(schedule)
        
        # Calcular conflictos de currículum para cada semestre.
        for semester, schedule in semester_schedule.items():
            violations['curriculum_conflict'] += self._curriculum_conflicts(schedule)
        
        # Verificar sobrecarga y disponibilidad de cada profesor.
        for professor, assigned_groups in groups_by_professor.items():
            # Restricción: Máximo de grupos por profesor.
            if not self.max_groups_by_professor(professor, assigned_groups):
                # La violación es la cantidad de grupos que exceden el límite.
                excess = len(assigned_groups) - professor.max_groups
                violations['professor_overload'] += excess

            # Restricción: Horario laboral del profesor.
            unavailable_count = self.professor_working_hours(professor, assigned_groups)
            violations['professor_unavailable'] += unavailable_count
        
        # Sumar todas las violaciones para obtener el total.
        total = sum(violations.values())
        return total, violations
    
    def _time_conflicts(self, schedule: List[Tuple[Group, BlockSchedule]]) -> int:
        """
        Cuenta el número de conflictos de tiempo en un horario dado (para un profesor o un aula).
        Un conflicto ocurre si dos o más eventos están programados en la misma hora.
        
        Args:
            schedule (List[Tuple[Group, BlockSchedule]]): Lista de tuplas (grupo, bloque_horario).
        
        Returns:
            int: El número de conflictos de tiempo encontrados.
        """
        # Diccionario para ver el uso de cada hora en cada día.{ 'Lunes': [0, 0, 1, 2, 1, ...]
        day_usage = {}
        
        for group, block_sched in schedule:
            day = block_sched.day
            
            # Si es la primera vez un día, lista de 24 horas con ceros.
            if day not in day_usage:
                day_usage[day] = [0] * 24
                
            block = block_sched.block
            start = block.start_hour
            end = block.end_hour

            # Para cada hora que dura el bloque, contador++
            for hour in range(start, end):
                if 0 <= hour < 24:
                    day_usage[day][hour] += 1
        
        conflicts = 0
        
        # contar los conflictos.
        for hours_list in day_usage.values():
            for count in hours_list:
                # Si una hora se usa más de una vez, hay un conflicto.
                if count > 1:
                    conflicts += (count - 1)
                    
        return conflicts

    # ==============================================================================================
    
    def _curriculum_conflicts(self, semester_schedule: List[Group]) -> int:
        if not semester_schedule:
            return 0
        
        courses_map = defaultdict(list)
        course_specs = {}
        for group in semester_schedule:
            courses_map[group.course.id].append(group)
            course_specs[group.course.id] = group.course.specialization.lower()
        
        general = [cid for cid, spec in course_specs.items() if spec == "general"]
        software = [cid for cid, spec in course_specs.items() if spec == "software"]
        cs = [cid for cid, spec in course_specs.items() if spec == "computer science"]
        it = [cid for cid, spec in course_specs.items() if spec == "information technology"]

        tracks = []
        if software: tracks.append(general + software)
        if cs: tracks.append(general + cs)
        if it: tracks.append(general + it)
        
        if not tracks and general:
            tracks.append(general)

        total_penalty = 0

        for track_courses in tracks:
            if len(track_courses) <= 1:
                continue

            course_groups_list = [courses_map[cid] for cid in track_courses]
            course_groups_list.sort(key=len)
            
            total_courses_in_track = len(course_groups_list)
            self._max_compatible_courses = 0 

            def backtrack(course_idx, current_occupied_blocks, count_taken):
                remaining_courses = total_courses_in_track - course_idx
                if count_taken + remaining_courses <= self._max_compatible_courses:
                    return

                if course_idx == total_courses_in_track:
                    if count_taken > self._max_compatible_courses:
                        self._max_compatible_courses = count_taken
                    return
                
                groups_available = course_groups_list[course_idx]
                for group in groups_available:
                    if not self._group_conflicts_with_blocks(group, current_occupied_blocks):
                        backtrack(course_idx + 1, current_occupied_blocks + group.schedules, count_taken + 1)

                backtrack(course_idx + 1, current_occupied_blocks, count_taken)

            backtrack(0, [], 0)
            total_penalty += (total_courses_in_track - self._max_compatible_courses)

        return total_penalty

    def _group_conflicts_with_blocks(self, group: Group, used_blocks: List[BlockSchedule]) -> bool:
        """Verificar si un grupo choca con una lista de bloques ocupados."""
        for g_block in group.schedules:
            for occupied in used_blocks:
                # Hay conflicto si coinciden en día y sus bloques de horas se solapan.
                if g_block.day == occupied.day and g_block.block.conflict(occupied.block):
                    return True
        return False

    # ==============================================================================================
    
    def max_groups_by_professor(self, professor: Professor, assigned_groups: List[Group]) -> bool:
        """tells if a professor has exceeded the maximum number of groups assigned

        Args:
            professor (Professor): the professor to check
            assigned_groups (List[Group]): the groups assigned to the prof

        Returns:
            bool: True if the professor has not exceeded the maximum number of groups, False otherwise
        """
        return len(assigned_groups) <= professor.max_groups

    def professor_working_hours(self, professor: Professor, assigned_groups: List[Group]) -> int:
        """Tells if a professor is scheduled within their working hours
        Args:
            professor (Professor): the professor to check
            assigned_groups (List[Group]): the groups assigned to the prof
        Returns:
            int: Number of invalid hours, the ones that are putside of the prof working hours
            """
        invalid_blocks = 0
        for group in assigned_groups:
            for block in group.schedules:
                # verifica si está disponible en un bloque específico.
                if not professor.is_available(block):
                    invalid_blocks += 1
        return invalid_blocks
    
    def get_detailed_report(self, groups: List[Group]) -> List[str]:
        """
        Genera un reporte de todas las violaciones duras.
        Uso: Llamar solo al final del programa para debug.
        """
        report = []
        
        # Re-organizar los datos para facilitar la generación del reporte.
        professor_schedule = defaultdict(list)
        classroom_schedule = defaultdict(list)
        groups_by_professor = defaultdict(list)
        
        for group in groups:
            if not group.schedules: continue
            
            if group.professor:
                groups_by_professor[group.professor].append(group)
                for block in group.schedules:
                    professor_schedule[group.professor.id].append((group, block))
            
            if group.classroom:
                for block in group.schedules:
                    classroom_schedule[group.classroom.number].append((group, block))

        # Reportar conflictos de profesores.
        for prof_id, items in professor_schedule.items():
            # Comparar cada par de bloques asignados al mismo profesor.
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    g1, b1 = items[i]
                    g2, b2 = items[j]
                    if g1.get_id() == g2.get_id(): continue # Un grupo no puede chocar consigo mismo.
                    
                    if b1.day == b2.day and b1.block.conflict(b2.block):
                        prof_name = g1.professor.name
                        msg = f"[PROFESOR] {prof_name} tiene choque: {g1.get_id()} vs {g2.get_id()} el {b1.day} a las {b1.block}"
                        if msg not in report: report.append(msg)

        # Reportar conflictos de aulas.
        for room_num, items in classroom_schedule.items():
            # Comparar cada par de bloques asignados a la misma aula.
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    g1, b1 = items[i]
                    g2, b2 = items[j]
                    if g1.get_id() == g2.get_id(): continue
                    
                    if b1.day == b2.day and b1.block.conflict(b2.block):
                        msg = f"[SALÓN] {room_num} tiene choque: {g1.get_id()} ({g1.course.name}) vs {g2.get_id()} ({g2.course.name}) el {b1.day} a las {b1.block}"
                        if msg not in report: report.append(msg)

        # Reportar violaciones de disponibilidad del profesor.
        for prof, assigned in groups_by_professor.items():
            for group in assigned:
                for block in group.schedules:
                    if not prof.is_available(block):
                        report.append(f"[DISPONIBILIDAD] {prof.name} no puede dar clase en horario asignado: {group.get_id()} el {block}")

        # Reportar sobrecarga de profesores.
        for prof, assigned in groups_by_professor.items():
            if len(assigned) > prof.max_groups:
                report.append(f"[SOBRECARGA] {prof.name} tiene {len(assigned)} grupos (Máx permitidos: {prof.max_groups})")

        return report