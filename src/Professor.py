from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple
from BlockSchedule import BlockSchedule
from Course import Course

@dataclass
class Professor:

    name: str
    id: str
    courses: Set[str] = field(default_factory=set)
    max_groups: int = 0
    course_preferences: List[Course] = field(default_factory=list)
    schedule_preferences: Dict[Tuple[str, int], BlockSchedule] = field(default_factory=dict)
    available_blocks: Dict[Tuple[str, int], BlockSchedule] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if not isinstance(other, Professor):
            return False
        return self.id == other.id
    
    def __repr__(self):
        return f"Professor({self.id}, {self.name})"

    def can_teach(self, course: Course) -> bool:
        return course.id in self.courses
    
    def is_available(self, block: BlockSchedule) -> bool:
        key = (block.day, block.block.start_hour)
        return key in self.available_blocks
    
    def prefers_schedule(self, block: BlockSchedule) -> bool:
        key = (block.day, block.block.start_hour)
        return key in self.schedule_preferences
    
    def prefers_course(self, course: Course) -> bool:
        return course in self.course_preferences