from DataLoader import DataLoader
from Schedule import *
from HardRestrictions import HardRestrictions
from SoftRestrictions import SoftRestrictions
from typing import List, Tuple
import itertools

def brute_force(loader: DataLoader) -> Schedule:
    """
    Generates a schedule using brute force search. Tests all possible
    combinations of class group assignments to find the one with the best fitness.
    
    Args:
        loader (DataLoader): data loader with input data
    
    Returns:
        Schedule: generated schedule with the best fitness found
    """
    # organize blocks by day
    blocks_by_day = {}
    for block in loader.time_blocks:
        blocks_by_day.setdefault(block.day, []).append(block)
    for day in blocks_by_day:
        blocks_by_day[day].sort(key=lambda b: b.block.start_hour)


    all_options, total_combinations = calc_total_combinations(loader, blocks_by_day)

    print(f"Total possible combination count: {total_combinations:,}")
    if total_combinations > 1_000_000:
        print("WARNING! This will take a VERY LONG time.")
        response = input("Do you want to continue? (y/n): ")
        if response.lower() != 'y' and response.lower() != 'yes':
            print("Aborting brute force search. Building random schedule instead.")
            return build_random_schedule(loader)

    hard_eval = HardRestrictions()
    soft_eval = SoftRestrictions()
    hard_weight = 1000.0
    soft_weight = 100.0

    best_schedule = None
    best_fitness = float('inf')
    evaluated = 0

    print("=== STARTING BRUTE FORCE ===")
    for combination in itertools.product(*all_options):
        schedule = create_empty_schedule()

        # build schedule from combination
        for group_info in combination:
            group = Group(
                course=group_info['course'],
                group_number=group_info['group_number'],
                professor=group_info['professor'],
                classroom=group_info['classroom'],
                schedules=group_info['schedules']
            )
            schedule.class_groups[group.get_id()] = group

        # eval schedule against fitness
        groups = list(schedule.class_groups.values())
        total_hard, hard_details = hard_eval.evaluate(groups)
        soft_penalty, soft_details = soft_eval.evaluate(groups)

        schedule.hard_violations = total_hard
        schedule.soft_violations = soft_details
        schedule.fitness_val = (total_hard * hard_weight) + (soft_penalty * soft_weight)

        if schedule.fitness_val < best_fitness:
            best_fitness = schedule.fitness_val
            best_schedule = schedule
            print("New best found:")
            print(f"    Fitness: {schedule.fitness_val:.2f} (evaluated: {evaluated:,})")

            if schedule.hard_violations == 0:
                print("\n Solución válida encontrada")
                return best_schedule
        evaluated += 1
        if evaluated % 10000 == 0:  # to make sure program isn't frozen
            print(f"Progress: {evaluated:,}/{total_combinations:,} ({100*evaluated/total_combinations:.2f}%)...")

    print(f"\n=== BRUTE FORCE COMPLETE ===")
    print(f"Evaluated: {evaluated:,} schedules")
    print(f"Best fitness: {best_fitness:.2f}")

    return best_schedule if best_schedule else build_random_schedule(loader)

# ==================================================================================================

def calc_total_combinations(loader: DataLoader, blocks_by_day: dict) -> Tuple[List, int]:
    """
    Calculates all possible group options and their total combination count.
    
    Args:
        loader (DataLoader): data loader with input
        blocks_by_day (dict): mapping of day to BlockSchedule list
    
    Returns:
        Tuple[List, int]: list of group options and total combination count
    """
    all_options = []
    total_combinations = 1

    for course in loader.courses:
        for group_number in range(1, course.groups + 1):
            professors = [p for p in loader.professors if course.id in p.courses]
            if not professors:
                print(f"WARNING! No professor available for course {course.id}")
                professors = [None]

            if course.lab:
                classrooms = [c for c in loader.classrooms if c.type == "lab"]
                if not classrooms:
                    classrooms = loader.clasrooms
            else:
                classrooms = loader.classrooms

            time_options = _gen_time_options(blocks_by_day, course.hours)

            group_options = []
            for professor in professors:
                for classroom in classrooms:
                    for schedules in time_options:
                        group_options.append({
                            'course': course,
                            'group_number': group_number,
                            'professor': professor,
                            'classroom': classroom,
                            'schedules': schedules
                        })

            all_options.append(group_options)
            total_combinations *= len(group_options)
    
    return all_options, total_combinations
    
# ==================================================================================================

def _gen_time_options(blocks_by_day: dict, required_hours: int) -> List[List]:
    """
    Generate all possible ways to schedule consecutive time blocks.

    Args:
        blocks_by_day (dict): mapping of day to list of BlockSchedule
        required_hours (int): number of consecutive hours needed

    Returns:
        List of possible schedule assignments, each a list of BlockSchedules.
    """
    options = []

    for day, day_blocks in blocks_by_day.items():
        for start_index in range(len(day_blocks) - required_hours + 1):
            schedules = []
            current_hour = day_blocks[start_index].block.start_hour
            schedules.append(day_blocks[start_index])

            valid = True
            for i in range(start_index + 1, len(day_blocks)):
                if len(schedules) >= required_hours:
                    break
                if day_blocks[i].block.start_hour == current_hour + 1:
                    schedules.append(day_blocks[i])
                    current_hour += 1
                else:   # gap
                    valid = False
                    break
            if valid and len(schedules) == required_hours:
                options.append(schedules)
    
    return options if options else [[]]