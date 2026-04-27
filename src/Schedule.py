from dataclasses import dataclass, field
import random
import math
import csv
import json
import os
from typing import Dict
from DataLoader import DataLoader
from Group import Group
from collections import defaultdict

@dataclass
class Schedule:

    class_groups: Dict[str, Group]
    fitness_val: float = float('inf')
    hard_violations: int = 0
    soft_violations: Dict[str, float] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        return self.hard_violations == 0

    def __repr__(self):
        status = "VALID" if self.is_valid() else "INVALID"
        return f"Schedule({status}, fitness_val={self.fitness_val:.2f}, groups={len(self.class_groups)})"

    # ==============================================================================================

    def to_dict(self) -> dict:
        """
        Converts the Schedule to a dictionary format suitable for JSON serialization.
        
        Returns:
            dict: dictionary representation of the Schedule
        """
        def consolidate(schedule_list):
            if not schedule_list:
                return []

            blocks_by_day = {}
            for s in schedule_list:
                blocks_by_day.setdefault(s.day, []).append(s)

            consolidated = []

            for day, blocks in blocks_by_day.items():
                blocks.sort(key=lambda s: s.block.start_hour)

                current_group = [blocks[0]]
                for i in range(1, len(blocks)):
                    prev = current_group[-1]
                    curr = blocks[i]
                    if curr.block.start_hour == prev.block.end_hour:
                        current_group.append(curr)
                    else:
                        consolidated.append({
                            'day': day,
                            'start_hour': current_group[0].block.start_hour,
                            'end_hour': current_group[-1].block.end_hour
                        })
                        current_group = [curr]

                # finalize last block group
                consolidated.append({
                    'day': day,
                    'start_hour': current_group[0].block.start_hour,
                    'end_hour': current_group[-1].block.end_hour
                })

            return consolidated

        return {
            'metadata': {
                'fitness_val': self.fitness_val,
                'hard_violations': self.hard_violations,
                'soft_violations': self.soft_violations,
                'is_valid': self.is_valid(),
                'total_groups': len(self.class_groups)
            },
            'groups': [
                {
                    'id': group.get_id(),
                    'course': {
                        'id': group.course.id,
                        'name': group.course.name,
                        'semester': group.course.semester,
                        'hours': group.course.hours,
                        'lab': group.course.lab
                    },
                    'group_number': group.group_number,
                    'professor': {
                        'id': group.professor.id,
                        'name': group.professor.name
                    } if group.professor else None,
                    'classroom': {
                        'number': group.classroom.number,
                        'type': group.classroom.type,
                    } if group.classroom else None,
                    'schedules': consolidate(group.schedules)
                }
                for group in self.class_groups.values()
            ]
        }

    # ==============================================================================================

    def to_json(self, filepath: str=None, indent: int=2) -> str:
        """
        Converts the Schedule to a JSON string and saves it to a file.
        
        Args:
            filepath(str, optional): path to save the JSON file. If None, does not save to file.
            indent(int, optional): number of spaces for indentation in JSON output. Default is 2.
        
        Returns:
            str: JSON string representation of the Schedule
        """
        data = self.to_dict()
        json_str = json.dumps(data, indent=indent)
        if filepath:
            dir = os.path.dirname(filepath)
            if dir:
                os.makedirs(dir, exist_ok=True)
            with open(filepath, 'w') as f:
                f.write(json_str)
            print(f"Schedule saved to {filepath}")
        return json_str

    # ==============================================================================================

    def to_csv(self, filepath: str):
            """
            Exports the schedule to a CSV file with one row per group.
            
            Args:
                filepath(str): path to save the CSV file
            """
            dir = os.path.dirname(filepath)
            if dir:
                os.makedirs(dir, exist_ok=True)
            
            fieldnames = [
                'group_id', 'course_id', 'course_name', 'semester', 'group_number',
                'professor_id', 'professor_name', 'classroom_number', 'classroom_type',
                'day_1', 'start_hour_1', 'end_hour_1',
                'day_2', 'start_hour_2', 'end_hour_2'
            ]

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for group in self.class_groups.values():
                    if not group.schedules:
                        continue
                    
                    row = {
                        'group_id': group.get_id(),
                        'course_id': group.course.id,
                        'course_name': group.course.name,
                        'semester': group.course.semester,
                        'group_number': group.group_number,
                        'professor_id': group.professor.id if group.professor else '',
                        'professor_name': group.professor.name if group.professor else '',
                        'classroom_number': group.classroom.number if group.classroom else '',
                        'classroom_type': group.classroom.type if group.classroom else '',
                        'day_1': '', 'start_hour_1': '', 'end_hour_1': '',
                        'day_2': '', 'start_hour_2': '', 'end_hour_2': ''
                    }

                    blocks_by_day = {}
                    for schedule in group.schedules:
                        blocks_by_day.setdefault(schedule.day, []).append(schedule)
                    
                    consolidated_schedules = []
                    sorted_days = sorted(blocks_by_day.keys(), key=lambda d: ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"].index(d))

                    for day in sorted_days:
                        blocks = blocks_by_day[day]
                        blocks.sort(key=lambda s: s.block.start_hour)
                        if blocks:
                            consolidated_schedules.append({
                                'day': day,
                                'start_hour': blocks[0].block.start_hour,
                                'end_hour': blocks[-1].block.end_hour,
                            })

                    if len(consolidated_schedules) >= 1:
                        row['day_1'] = consolidated_schedules[0]['day']
                        row['start_hour_1'] = consolidated_schedules[0]['start_hour']
                        row['end_hour_1'] = consolidated_schedules[0]['end_hour']

                    if len(consolidated_schedules) >= 2:
                        row['day_2'] = consolidated_schedules[1]['day']
                        row['start_hour_2'] = consolidated_schedules[1]['start_hour']
                        row['end_hour_2'] = consolidated_schedules[1]['end_hour']
                    writer.writerow(row)
            
            print(f"Schedule saved to {filepath}")

    def append_group(self, group: Group):
        self.class_groups[group.get_id()] = group
# ==================================================================================================

def create_empty_schedule() -> Schedule:
    """
    Wrapper function to create an empty Schedule.
    
    Returns:
        Schedule: empty Schedule object
    """
    return Schedule(class_groups={})

# ==================================================================================================

DAY_PAIRS = {
    "Lunes": ["Jueves"],
    "Jueves": ["Lunes"],
    "Martes": ["Viernes"],
    "Viernes": ["Martes"],
    "Miércoles": ["Lunes", "Viernes"] 
}

DAY_WEIGHTS = {
    "Lunes": 2,
    "Martes": 2,
    "Miércoles": 1,
    "Jueves": 2,
    "Viernes": 2
}

def _find_consecutive_blocks(day_blocks: list, start_index: int, hours_needed: int) -> list | None:
    """
    Intenta encontrar un número de bloques horarios consecutivos.
    Retorna la lista de bloques si tiene éxito, o None si falla.
    """
    if start_index >= len(day_blocks):
        return None

    schedules = [day_blocks[start_index]]
    current_hour = day_blocks[start_index].block.start_hour

    if hours_needed == 1:
        return schedules

    for b in day_blocks[start_index + 1:]:
        if b.block.start_hour == current_hour + 1:
            schedules.append(b)
            current_hour += 1
            if len(schedules) == hours_needed:
                return schedules  
        else:
            return None 

    return None 


def build_random_schedule(loader: DataLoader) -> Schedule:
    """
    Builds a random schedule by assigning random professors, classrooms,
    and time blocks to each class group.
    
    Args:
        loader (DataLoader): data loader with input data

    Returns:
        Schedule: generated random schedule
    """
    schedule = create_empty_schedule()

    blocks_by_day = {}
    for block in loader.time_blocks:
        blocks_by_day.setdefault(block.day, []).append(block)

    for day in blocks_by_day:
        blocks_by_day[day].sort(key=lambda b: b.block.start_hour)

    all_days = list(DAY_WEIGHTS.keys())
    day_weights_values = list(DAY_WEIGHTS.values())

    for course in loader.courses:
        for gnum in range(1, course.groups + 1):
            profs = [p for p in loader.professors if course.id in p.courses]
            professor = random.choice(profs) if profs else None

            if course.lab:
                labs = [r for r in loader.classrooms if r.type == "lab"]
                classroom = random.choice(labs) if labs else random.choice(loader.classrooms)
            else:
                classroom = random.choice(loader.classrooms)

            schedules = []
            
            if course.hours <= 3:
                while True: 
                    day = random.choices(all_days, weights=day_weights_values, k=1)[0]
                    day_blocks = blocks_by_day.get(day, [])
                    
                    if not day_blocks: continue

                    start_index = random.randrange(len(day_blocks))
                    
                    found_blocks = _find_consecutive_blocks(day_blocks, start_index, course.hours)
                    
                    if found_blocks:
                        schedules = found_blocks
                        break

            else:
                hours_day1 = math.ceil(course.hours / 2)
                hours_day2 = course.hours - hours_day1
                
                while True: 
                    day1 = random.choices(all_days, weights=day_weights_values, k=1)[0]
                    day2 = random.choice(DAY_PAIRS[day1])
                    
                    day1_blocks = blocks_by_day.get(day1, [])
                    day2_blocks = blocks_by_day.get(day2, [])

                    if not day1_blocks or not day2_blocks: continue
                    
                    start_index1 = random.randrange(len(day1_blocks))
                    
                    blocks1 = _find_consecutive_blocks(day1_blocks, start_index1, hours_day1)
                    
                    if not blocks1:
                        continue 
                    start_hour_needed = blocks1[0].block.start_hour
                    start_index2 = -1
                    for i, block in enumerate(day2_blocks):
                        if block.block.start_hour == start_hour_needed:
                            start_index2 = i
                            break
                    
                    if start_index2 == -1:
                        continue 
                    blocks2 = _find_consecutive_blocks(day2_blocks, start_index2, hours_day2)

                    if blocks2:
                        schedules = blocks1 + blocks2
                        break 
            group = Group(
                course=course,
                group_number=gnum,
                professor=professor,
                classroom=classroom,
                schedules=schedules
            )
            schedule.class_groups[group.get_id()] = group

    return schedule