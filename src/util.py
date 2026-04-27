
from enum import Enum, auto, unique, IntEnum, StrEnum


class DAYS(StrEnum):
    MONDAY = "Lunes"
    TUESDAY = "Martes"
    WEDNESDAY = "Miércoles"
    THURSDAY = "Jueves"
    FRIDAY = "Viernes"
    SATURDAY = "Sábado"
    SUNDAY = "Domingo"

class PROFESSOR_FIELDS(StrEnum):
    ID = "id"
    NAME = "name"
    COURSES = "courses"
    MAX_GROUPS = "max_groups"
    COURSE_PREFERENCE = "course_preference"
    SCHEDULE_PREFERENCE = "schedule_preference"
    AVAILABLE_BLOCKS = "available_blocks"

# def parse_to_minutes(time_str: str) -> int:
    
#     hours, minutes = map(int, time_str.split(":"))
#     return hours * 60 + minutes
