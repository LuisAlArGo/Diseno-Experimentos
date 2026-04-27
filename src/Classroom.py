from dataclasses import dataclass

@dataclass
class Classroom:

    number: str
    type: str

    def __hash__(self):
        return hash(self.number)

    def __eq__(self, other):
        if not isinstance(other, Classroom):
            return False
        return self.number == other.number
    
    def __repr__(self):
        return f"Classroom({self.number}, {self.type})"
