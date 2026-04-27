import json
import os
from typing import List, Dict, Tuple
from Classroom import Classroom
from Course import Course
from Professor import Professor
from BlockSchedule import BlockSchedule, TimeBlock
from util import *

PROFESSORS_FILE = "professors.json"
COURSES_FILE = "courses.json"
CLASSROOMS_FILE = "classrooms.json"

class DataLoader:
    """
    Class responsible for loading data from JSON files into the application's data structures.
    Attributes:
        path (str): The base path where the JSON data files are located.
        classrooms (List[Classroom]): List of Classroom objects loaded from the data.
        courses (List[Course]): List of Course objects loaded from the data.
        professors (List[Professor]): List of Professor objects loaded from the data.
        time_blocks (List[BlockSchedule]): List of BlockSchedule objects representing time blocks.
    Methods:
        load_all(): Loads all data types (classrooms, courses, professors) from their respective JSON files.
        load_classrooms(file_path: str): Loads classroom data from a specified JSON file.
        load_courses(file_path: str): Loads course data from a specified JSON file.
        load_professors(file_path: str): Loads professor data from a specified JSON file.
        _generate_blockSchedules(days: List[str], start_hour: int, end_hour: int): Generates time blocks for scheduling.
        _get_blocks_in_range(day: str, start_time: str, end_time: str) -> List[BlockSchedule]: 
            Retrieves time blocks within a specified time range on a given day.

    """


    def __init__(self, data_path: str):
        """Initializes the DataLoader with the given data path.

        Args:
            data_path (str): The base path where the JSON data files are located.
        """
        self.path = data_path
        """
        Base path where the JSON data files are located.
        """
        self.classrooms: List[Classroom] = []
        """
        List of Classroom objects loaded from the data.
        """
        self.courses: List[Course] = []
        """
        List of Course objects loaded from the data.
        """
        self.professors: List[Professor] = []
        """
        List of Professor objects loaded from the data.
        """
        self.time_blocks: List[BlockSchedule] = []
        """
        List of BlockSchedule objects representing time blocks.
        """
        self._courses_by_id: Dict[str, Course] = {}
        """
        Dictionary mapping course IDs to Course objects for quick lookup.
        """

    def load_all(self):
        """Loads all data types (classrooms, courses, professors) from their respective JSON files.

        Raises:
            FileNotFoundError: If the data path does not exist.
        """
        self._generate_blockSchedules()
        if (os.path.exists(self.path) == False):
            raise FileNotFoundError(f"Data path {self.path} does not exist.")
        self.load_classrooms(f"{self.path}/{CLASSROOMS_FILE}")
        self.load_courses(f"{self.path}/{COURSES_FILE}")
        self.load_professors(f"{self.path}/{PROFESSORS_FILE}")

    def _generate_blockSchedules(self, days: List[str] = [], start_hour: int = 7, end_hour: int = 23):
        """Generates time blocks for scheduling.
        Args:
            days (List[str], optional): List of days to generate blocks for. Defaults to all weekdays.
            start_hour (int, optional): Starting hour for block generation. Defaults to 7.
            end_hour (int, optional): Ending hour for block generation. Defaults to 23.
        """
        if not days:
            days = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]

        block_duration = 1
        for day in days:
            for hour in range(start_hour, end_hour):
                # if  hour + block_duration > end_hour:
                #     continue
                # print("--- day ---", day)
                # print("--- hour ---", hour)
                # print("--- block_duration ---", block_duration)
                # print("--- end_hour ---", end_hour)
                time_block = TimeBlock(
                    start_hour=hour, end_hour=hour+block_duration)
                # print("--- time_block ---", time_block)
                block_schedule = BlockSchedule(day=day, block=time_block)
                self.time_blocks.append(block_schedule)

    def _get_blocks_in_range(self, day: str, start_time: int, end_time: int) -> List[BlockSchedule]:
        """Retrieves time blocks within a specified time range on a given day.
        Args:
            day (str): The day to filter blocks by.
            start_time (int): The start time as an hour.
            end_time (int): The end time as an hour.
        Returns:
            List[BlockSchedule]: List of BlockSchedule objects within the specified time range.
        """
        blocks_in_range: List[BlockSchedule] = []
        # print("--- self.time_blocks ---", self.time_blocks)
        for block in self.time_blocks:
            # print("--- block ---", block)
            if block.day == day and block.block.start_hour >= start_time and block.block.end_hour <= end_time:
                blocks_in_range.append(block)
                # print("--- blocks_in_range ---", blocks_in_range)

        return blocks_in_range

    def load_classrooms(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.classrooms = [Classroom(**c) for c in data]

    def load_courses(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.courses = [Course(**c) for c in data]
            self._courses_by_id = {c.id: c for c in self.courses}

    def load_professors(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for prof_data in data:
                course_prefs: List[Course] = [
                    self._courses_by_id[course_id] for course_id in prof_data.get("course_preferences", [])
                    if course_id in self._courses_by_id
                ]

                schedule_prefs: Dict[Tuple[str, int], BlockSchedule] = {}
                for pref_range in prof_data.get("schedule_preferences", []):
                    # print("--- pref_range ---", pref_range)
                    blocks = self._get_blocks_in_range(
                        pref_range["day"], pref_range["start_time"], pref_range["end_time"])
                    for block in blocks:
                        key = (block.day, block.block.start_hour)
                        schedule_prefs[key] = block

                available_blocks: Dict[Tuple[str, int], BlockSchedule] = {}
                for avail_range in prof_data.get("available_blocks", []):
                    blocks = self._get_blocks_in_range(
                        avail_range["day"], avail_range["start_time"], avail_range["end_time"])
                    for block in blocks:
                        key = (block.day, block.block.start_hour)
                        available_blocks[key] = block

                professor = Professor(
                    id=prof_data["id"],
                    name=prof_data["name"],
                    courses=set(prof_data.get("courses", [])),
                    max_groups=prof_data["max_groups"],
                    course_preferences=course_prefs,
                    schedule_preferences=schedule_prefs,
                    available_blocks=available_blocks,
                )
                self.professors.append(professor)
