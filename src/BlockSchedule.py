from dataclasses import dataclass

@dataclass(frozen=True)
class TimeBlock:

    start_hour: int
    end_hour: int

    def conflict(self, other: 'TimeBlock') -> bool:
        return self.start_hour < other.end_hour and self.end_hour > other.start_hour
    
    def __repr__(self):
        return f"{self.start_hour:02d}:00-{self.end_hour:02d}:00"

@dataclass(frozen=True)
class BlockSchedule:

    day: str
    block: TimeBlock
    
    def __hash__(self):
        return hash((self.day, self.block))
    
    def __eq__(self, other):
        return self.day == other.day and self.block == other.block
    
    def __repr__(self):
        return f"{self.day} {self.block}"
    
    def can_schedule(self, other: 'BlockSchedule') -> bool:
        if self.block.start_hour >= other.block.end_hour or self.block.end_hour <= other.block.start_hour:
            return True
        return False
