from typing import List, Optional
from dataclasses import dataclass, field
from Course import Course
from Professor import Professor
from Classroom import Classroom
from BlockSchedule import BlockSchedule

@dataclass
class Group:

    course: Course
    group_number: int
    professor: Optional[Professor] = None
    classroom: Optional[Classroom] = None
    schedules: List[BlockSchedule] = field(default_factory=list)

    def get_id(self):
        return f"{self.course.id}-G{self.group_number}"

    def __hash__(self):
        return hash(self.get_id())

    def __eq__(self, other):
        return self.get_id() == other.get_id()
    
    def __repr__(self):
        prof = self.professor.name if self.professor else "No Prof"
        room = self.classroom.number if self.classroom else "No Room"

        sched = [str(b) for b in self.schedules]
        sched_str = ", ".join(sched) if sched else "No Schedule"

        return f"Group({self.get_id()}, {prof}, {room}, [{sched_str}])"

    def is_complete(self) -> bool:
        return (self.professor is not None and 
                self.classroom is not None and 
                len(self.schedules) > 0)
    
    def get_total_hours(self) -> int:
        return len(self.schedules)
    
    def conflicts_with(self, other: 'Group') -> bool:
        if not self.schedules or not other.schedules:
            return False
        
        for block1 in self.schedules:
            for block2 in other.schedules:
                if block1.day == block2.day and block1.block.conflict(block2.block):
                    return True
        return False
    
    def clone(self):
        """
        Crea una copia superficial segura del Grupo.
        Mantiene referencias a Course, Professor y Classroom (que no cambian sus propiedades internas),
        pero crea una nueva lista de schedules.
        """
        new_group = Group(
            course=self.course,
            group_number=self.group_number,
            professor=self.professor,
            classroom=self.classroom,
            schedules=list(self.schedules) 
        )
        return new_group
