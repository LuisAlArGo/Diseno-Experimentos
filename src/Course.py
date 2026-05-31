from dataclasses import dataclass

@dataclass
class Course:

    id: str
    name: str
    semester: int
    hours: int
    lab: bool
    groups: int 
    specialization: str
    
    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Course):
            return False
        return self.id == other.id
    
    def __repr__(self):
        return f"Course({self.id}, {self.name}, Sem{self.semester}, {self.specialization})"