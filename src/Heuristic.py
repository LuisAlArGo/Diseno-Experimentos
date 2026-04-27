
from collections import defaultdict
import pprint
from DataLoader import DataLoader
from Course import *
from Professor import *
from Classroom import *
from BlockSchedule import *
from Schedule import *
from HardRestrictions import HardRestrictions
from SoftRestrictions import SoftRestrictions
from typing import Any, List, Tuple
import heapq
from enum import Enum, auto, StrEnum

# Source - https://stackoverflow.com/a
# Posted by Alexander C, modified by community. See post 'Timeline' for change history
# Retrieved 2025-11-27, License - CC BY-SA 4.0
# modified by @jorart10
import os
import sys
class HiddenPrints:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def __enter__(self):
        if not self.verbose:  # only hide prints when verbose=False
            self._original_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.verbose:
            sys.stdout.close()
            sys.stdout = self._original_stdout



priority_weights = {
    'professor_preference': 5.0,
    'classroom_preference': 3.0,
    'time_preference': 2.0
}


class AvailabilityType(Enum):
    free_prof_blocks = auto()
    free_room_blocks = auto()
    blocks_by_day = auto()
    block_lookup = auto()
    profs_for_course = auto()
    rooms_by_type = auto()
    prof_obj_map = auto()
    room_obj_map = auto()


def heuristic_schedule(loader: DataLoader, hard_weight: float, soft_weight: float, max_backtracks: int = 500, verbose: bool = False) -> Schedule:
    """Generate a schedule with zero hard restriction violations using MRV heuristic with backtracking.

    Args:
        loader (DataLoader): Data loader with courses, professors, classrooms, time blocks
        hard_weight: Weight for hard violations in fitness calculation
        soft_weight: Weight for soft violations in fitness calculation

    Returns:
        Schedule: A valid schedule with no hard violations
    """

    # Placeholder heuristic function
    schedule: Schedule = create_empty_schedule()
    hard_eval = HardRestrictions()
    soft_eval = SoftRestrictions()

    # build availability structures for getting number of options by course and later on assignment
    availability: dict[AvailabilityType, dict] = build_availability(loader)

    # Track assignments for backtracking
    assignment_stack: List[Tuple[Group, Dict[str, Any]]] = []

    # courses with less total options get scheduled first
    # course_n_options: List[Tuple[int, str, Course]] = []  # (options, course_id, course)
    course_n_options: List[Tuple[int, str, Course]] = []
    for course in loader.courses:
        total_options = 0
        # professors who can teach the course
        for professor in loader.professors:
            if professor.can_teach(course):
                total_options += 1
                # time blocks available to professor
                for block_key in availability[AvailabilityType.free_prof_blocks].get(professor.id, []):
                    block = availability[AvailabilityType.block_lookup][block_key]
                    if course.hours <= (block.block.end_hour - block.block.start_hour):
                        total_options += 1
        # classrooms that fit the course
        for classroom in loader.classrooms:
            for room_type in availability[AvailabilityType.rooms_by_type]:
                if classroom.type in availability[AvailabilityType.rooms_by_type][room_type]:
                    total_options += 1
        # TODO: finish all options calculation if needed (im not sure if this is enough)
        heapq.heappush(course_n_options, (total_options, course.id, course))

    # Track which groups still need assignment
    unassigned_groups = []

    # Iterate through courses in order of least options and assign groups Greedily in available slots
    while course_n_options:
        # get the tuple and ignore the number of options and course id
        _, _, course = heapq.heappop(course_n_options)
        for group_number in range(1, course.groups + 1):
            # Create group with no assignments yet
            group = Group(
                course=course,
                group_number=group_number,
                professor=None,
                classroom=None,
                schedules=[]
            )

            # Get list of professors who can teach this course
            prof_ids = availability[AvailabilityType.profs_for_course].get(
                course.id, [])
            if not prof_ids:
                print(
                    f"WARNING: No professors available for course {course.id}")
                continue

            # Determine which rooms are suitable (lab or all)
            if course.lab:
                room_ids = availability[AvailabilityType.rooms_by_type].get(
                    'lab', [])
            else:
                room_ids = availability[AvailabilityType.rooms_by_type].get(
                    'all', [])

            if not room_ids:
                print(f"WARNING: No suitable rooms for course {course.id}")
                continue

            # Try to find a valid assignment with backtracking
            assigned = False
            backtrack_count = 0
            tried_options = set()  # Track (prof_id, room_id, tuple(block_keys)) to avoid retrying

            while not assigned:
                found_any_option = False

                for prof_id in prof_ids:
                    if assigned:
                        break

                    prof_obj = availability[AvailabilityType.prof_obj_map].get(
                        prof_id)
                    if not prof_obj:
                        continue

                    prof_free_blocks = availability[AvailabilityType.free_prof_blocks].get(
                        prof_id, set())

                    # Try each day to find contiguous blocks
                    for day, day_blocks in availability[AvailabilityType.blocks_by_day].items():
                        if assigned:
                            break

                        # Try to find contiguous sequence of required hours
                        for i in range(len(day_blocks) - course.hours + 1):
                            candidate_blocks = day_blocks[i:i + course.hours]

                            # Check if blocks are contiguous
                            is_contiguous = True
                            for j in range(len(candidate_blocks) - 1):
                                if candidate_blocks[j].block.end_hour != candidate_blocks[j+1].block.start_hour:
                                    is_contiguous = False
                                    break

                            if not is_contiguous:
                                continue

                            # Check if professor is free for all these blocks
                            block_keys = [(b.day, b.block.start_hour)
                                          for b in candidate_blocks]
                            if not all(k in prof_free_blocks for k in block_keys):
                                continue

                            # Try to find a free room for these blocks
                            for room_id in room_ids:
                                room_free_blocks = availability[AvailabilityType.free_room_blocks].get(
                                    room_id, set())
                                if not all(k in room_free_blocks for k in block_keys):
                                    continue

                                # Check if we've already tried this option
                                option_key = (prof_id, room_id,
                                              tuple(block_keys))
                                if option_key in tried_options:
                                    continue

                                found_any_option = True

                                # Create a test group to validate hard restrictions
                                room_obj = availability[AvailabilityType.room_obj_map].get(
                                    room_id)
                                if not room_obj:
                                    continue

                                test_group = Group(
                                    course=course,
                                    group_number=group_number,
                                    professor=prof_obj,
                                    classroom=room_obj,
                                    schedules=candidate_blocks
                                )

                                # Validate no hard restrictions would be violated
                                test_groups = list(
                                    schedule.class_groups.values()) + [test_group]
                                hard_violations, _ = hard_eval.evaluate(
                                    test_groups)

                                if hard_violations == 0:
                                    # Valid assignment - apply it
                                    option = {
                                        'prof_id': prof_id,
                                        'room_id': room_id,
                                        'blocks': candidate_blocks
                                    }
                                    tried_options.add(option_key)
                                    success = assign_option(
                                        schedule, group, option, availability)
                                    if success:
                                        assignment_stack.append(
                                            (group, option))
                                        with HiddenPrints(verbose=verbose):
                                            print(f"\tSuccessfully assigned {course.id}-G{group_number}")
                                        assigned = True
                                        break
                                else:
                                    # This option violates hard constraints, mark as tried
                                    tried_options.add(option_key)

                # If no valid assignment found, try backtracking
                if not assigned:
                    if assignment_stack and backtrack_count < max_backtracks and found_any_option:
                        # Undo last assignment
                        last_group, last_option = assignment_stack.pop()
                        with HiddenPrints(verbose=verbose):
                            print(f"Backtracking for {course.id}-G{group_number}... (attempt {backtrack_count + 1})")
                        undo_assignment(schedule, last_group,
                                        last_option, availability)
                        backtrack_count += 1
                    else:
                        # No more options to backtrack or exceeded limit
                        if not found_any_option:
                            print(
                                f"WARNING: Could not assign {course.id}-G{group_number} in first pass (tried {len(tried_options)} options)")
                        else:
                            print(
                                f"WARNING: Could not assign {course.id}-G{group_number} in first pass (backtracked {backtrack_count} times)")
                        break

            # Track unassigned groups for second pass
            if not assigned:
                unassigned_groups.append((course, group_number))

    # Check which groups are actually missing from the schedule (may have been removed during backtracking)
    missing_groups = []
    for course in loader.courses:
        for group_number in range(1, course.groups + 1):
            group_id = f"{course.id}-G{group_number}"
            if group_id not in schedule.class_groups:
                missing_groups.append((course, group_number))

    # Second pass: Try to assign any groups that were skipped or removed during backtracking
    if missing_groups:
        with HiddenPrints(verbose=verbose):
            print(f"\n=== Second pass: attempting to assign {len(missing_groups)} missing groups ===")
        unassigned_groups = missing_groups

        for course, group_number in unassigned_groups:
            with HiddenPrints(verbose=verbose):
                print(f"Retrying {course.id}-G{group_number}...")
            # Similar assignment logic but without backtracking
            group = Group(course=course, group_number=group_number,
                          professor=None, classroom=None, schedules=[])

            prof_ids = availability[AvailabilityType.profs_for_course].get(
                course.id, [])
            room_ids = availability[AvailabilityType.rooms_by_type].get(
                'lab' if course.lab else 'all', [])

            assigned = False
            for prof_id in prof_ids:
                if assigned:
                    break
                prof_obj = availability[AvailabilityType.prof_obj_map].get(
                    prof_id)
                if not prof_obj:
                    continue
                prof_free_blocks = availability[AvailabilityType.free_prof_blocks].get(
                    prof_id, set())

                for day, day_blocks in availability[AvailabilityType.blocks_by_day].items():
                    if assigned:
                        break
                    for i in range(len(day_blocks) - course.hours + 1):
                        candidate_blocks = day_blocks[i:i + course.hours]
                        is_contiguous = all(candidate_blocks[j].block.end_hour == candidate_blocks[j+1].block.start_hour
                                            for j in range(len(candidate_blocks) - 1))
                        if not is_contiguous:
                            continue

                        block_keys = [(b.day, b.block.start_hour)
                                      for b in candidate_blocks]
                        if not all(k in prof_free_blocks for k in block_keys):
                            continue

                        for room_id in room_ids:
                            room_free_blocks = availability[AvailabilityType.free_room_blocks].get(
                                room_id, set())
                            if not all(k in room_free_blocks for k in block_keys):
                                continue

                            room_obj = availability[AvailabilityType.room_obj_map].get(
                                room_id)
                            if not room_obj:
                                continue

                            test_group = Group(course=course, group_number=group_number, professor=prof_obj,
                                               classroom=room_obj, schedules=candidate_blocks)
                            test_groups = list(
                                schedule.class_groups.values()) + [test_group]
                            hard_violations, _ = hard_eval.evaluate(
                                test_groups)

                            if hard_violations == 0:
                                option = {
                                    'prof_id': prof_id, 'room_id': room_id, 'blocks': candidate_blocks}
                                if assign_option(schedule, group, option, availability):
                                    assigned = True
                                    break

            if not assigned:
                print(
                    f"  ERROR: Could not assign {course.id}-G{group_number} even in second pass")

    hard_eval = HardRestrictions()
    soft_eval = SoftRestrictions()
    hard_weight = 1000.0
    soft_weight = 100.0
    # eval schedule against fitness
    groups = list(schedule.class_groups.values())
    total_hard, hard_details = hard_eval.evaluate(groups)
    soft_penalty, soft_details = soft_eval.evaluate(groups)

    schedule.hard_violations = total_hard
    schedule.soft_violations = soft_details
    schedule.fitness_val = (total_hard * hard_weight) + \
        (soft_penalty * soft_weight)
    return schedule

# ==================================================================================================
# TODO: add semester-wise curriculum conflict checks. Soft restrictions can be added and given prioirty to hard ones and once softs run out, consume hard ones


def build_availability(loader) -> Dict[AvailabilityType, Any]:
    """Build availability structures from loader.

    Returns a dict with:
      - free_prof_blocks: {prof_id: set((day, start_hour), ...)}
      - free_room_blocks: {room_number: set((day, start_hour), ...)}
      - blocks_by_day: {day: [BlockSchedule, ...]}
      - block_lookup: {(day, start_hour): BlockSchedule}
      - profs_for_course: {course_id: [prof_ids...]}
      - rooms_by_type: {'lab': [room_numbers], 'theory': [room_numbers], 'all': [room_numbers]}
      - prof_obj_map: {prof_id: Professor}
      - room_obj_map: {room_number: Classroom}
    """
    free_prof_blocks: Dict[str, Set[Tuple[str, int]]] = {}
    prof_obj_map: Dict[str, Professor] = {}
    profs_for_course: Dict[str, List[str]] = defaultdict(list)

    for prof in loader.professors:
        prof_obj_map[prof.id] = prof
        # professor.available_blocks uses keys (day, start_hour)
        free_prof_blocks[prof.id] = set(
            prof.available_blocks.keys()) if prof.available_blocks else set()
        for c_id in prof.courses:
            profs_for_course[c_id].append(prof.id)

    # build block lookup and blocks_by_day
    block_lookup: Dict[Tuple[str, int], BlockSchedule] = {}
    blocks_by_day: Dict[str, List[BlockSchedule]] = defaultdict(list)
    for b in loader.time_blocks:
        key = (b.day, b.block.start_hour)
        block_lookup[key] = b
        blocks_by_day[b.day].append(b)

    # sort blocks per day by start_hour
    for day in blocks_by_day:
        blocks_by_day[day].sort(key=lambda x: x.block.start_hour)

    # rooms availability: initially all rooms are free for all blocks
    all_block_keys = set(block_lookup.keys())
    free_room_blocks: Dict[str, Set[Tuple[str, int]]] = {}
    rooms_by_type: Dict[str, List[str]] = defaultdict(list)
    room_obj_map: Dict[str, Classroom] = {}

    for room in loader.classrooms:
        room_obj_map[room.number] = room
        free_room_blocks[room.number] = set(all_block_keys)
        if room.type == 'lab':
            rooms_by_type['lab'].append(room.number)
        rooms_by_type['all'].append(room.number)

    return {
        AvailabilityType.free_prof_blocks: free_prof_blocks,
        AvailabilityType.free_room_blocks: free_room_blocks,
        AvailabilityType.blocks_by_day: blocks_by_day,
        AvailabilityType.block_lookup: block_lookup,
        AvailabilityType.profs_for_course: profs_for_course,
        AvailabilityType.rooms_by_type: rooms_by_type,
        AvailabilityType.prof_obj_map: prof_obj_map,
        AvailabilityType.room_obj_map: room_obj_map,
    }

# ==================================================================================================

# TODO: check for maximums


def assign_option(schedule: Schedule, group: Group, option: Dict[str, Any], avail: Dict[AvailabilityType, Any]) -> bool:
    """Apply option: assign professor, classroom, and schedule blocks to group, add to schedule, update availability.

    Args:
        schedule: The schedule to add the group to
        group: The Group object (may have None professor/classroom/schedules initially)
        option: Dict with 'prof_id', 'room_id', 'blocks' keys
        avail: Availability structure from build_availability

    Returns:
        True if assignment was successful, False otherwise
    """
    prof_id = option['prof_id']
    room_id = option['room_id']
    blocks: List[BlockSchedule] = option['blocks']

    # Look up professor and classroom objects from availability maps
    prof_obj = avail[AvailabilityType.prof_obj_map].get(prof_id)
    room_obj = avail[AvailabilityType.room_obj_map].get(room_id)

    if not prof_obj or not room_obj:
        print(
            f"WARNING: Could not find professor {prof_id} or classroom {room_id} in availability maps")
        return False

    # Assign professor, classroom, and schedules to the group
    group.professor = prof_obj
    group.classroom = room_obj
    group.schedules = blocks

    # Add group to schedule
    schedule.class_groups[group.get_id()] = group

    # Remove blocks from availability
    keys = [(b.day, b.block.start_hour) for b in blocks]
    # prof
    if prof_id in avail[AvailabilityType.free_prof_blocks]:
        for k in keys:
            avail[AvailabilityType.free_prof_blocks][prof_id].discard(k)
    # room
    if room_id in avail[AvailabilityType.free_room_blocks]:
        for k in keys:
            avail[AvailabilityType.free_room_blocks][room_id].discard(k)

    return True

# ==================================================================================================


def undo_assignment(schedule: Schedule, group: Group, option: Dict[str, Any], avail: Dict[AvailabilityType, Any]) -> None:
    """Undo an assignment: remove group from schedule and restore availability.

    Args:
        schedule: The schedule to remove the group from
        group: The Group object to remove
        option: Dict with 'prof_id', 'room_id', 'blocks' keys
        avail: Availability structure from build_availability
    """
    # Remove group from schedule
    group_id = group.get_id()
    if group_id in schedule.class_groups:
        del schedule.class_groups[group_id]    # Restore blocks to availability
    prof_id = option['prof_id']
    room_id = option['room_id']
    blocks: List[BlockSchedule] = option['blocks']
    keys = [(b.day, b.block.start_hour) for b in blocks]

    # Restore professor availability
    if prof_id in avail[AvailabilityType.free_prof_blocks]:
        for k in keys:
            avail[AvailabilityType.free_prof_blocks][prof_id].add(k)

    # Restore room availability
    if room_id in avail[AvailabilityType.free_room_blocks]:
        for k in keys:
            avail[AvailabilityType.free_room_blocks][room_id].add(k)

# ==================================================================================================


def check_availability(professor: Professor, block: BlockSchedule) -> bool:
    key = (block.day, block.block.start_hour)
    return key in professor.available_blocks


# ==================================================================================================
# Example usage for testing
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Heuristic Scheduler")
    parser.add_argument('--data-path', type=str, required=True,
                        help='Path to the data directory')
    args = parser.parse_args()
    loader = DataLoader(args.data_path)
    loader.load_all()

    #
    availability = build_availability(loader)
    schedule = create_empty_schedule()
    s = pprint.pformat(availability)
    with open("availability_debug.txt", "w") as f:
        f.write(s)

    # Create a test group
    test_group = Group(
        course=loader.courses[0],
        group_number=1,
        professor=None,
        classroom=None,
        schedules=[]
    )

    assign_option(schedule,
                  group=test_group,
                  option={
                      'prof_id': loader.professors[0].id,
                      'room_id': loader.classrooms[0].number,
                      'blocks': [loader.time_blocks[i] for i in range(5)]
                  },
                  avail=availability)

    s = pprint.pformat(availability)
    with open("availability_debug_after_assign_option.txt", "w") as f:
        f.write(s)

    pprint.pprint(schedule.to_dict())

    print("Running heuristic scheduler...")
    schedule = heuristic_schedule(
        loader, hard_weight=1000.0, soft_weight=100.0)
    print("Generated Schedule:", schedule)
    pprint.pformat(schedule.to_json())
    print("Hard Violations:", schedule.hard_violations)
    print("Fitness Value:", schedule.fitness_val)
    with open("heuristic_schedule.json", "w") as f:
        f.write(schedule.to_json())
