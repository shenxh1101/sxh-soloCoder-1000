from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict


@dataclass
class FileInfo:
    path: Path
    size: int
    created: datetime
    modified: datetime
    extension: str
    file_type: str = "other"
    is_temporary: bool = False
    file_hash: Optional[str] = None
    category: str = "uncategorized"

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size_human(self) -> str:
        return format_size(self.size)


@dataclass
class DuplicateGroup:
    file_hash: str
    files: List[FileInfo] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def wasted_size(self) -> int:
        if len(self.files) <= 1:
            return 0
        return self.total_size - self.files[0].size


@dataclass
class ScanResult:
    files: List[FileInfo] = field(default_factory=list)
    empty_dirs: List[Path] = field(default_factory=list)
    duplicates: List[DuplicateGroup] = field(default_factory=list)
    temp_files: List[FileInfo] = field(default_factory=list)
    excluded: List[Path] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def total_count(self) -> int:
        return len(self.files)

    @property
    def duplicates_size(self) -> int:
        return sum(d.wasted_size for d in self.duplicates)

    @property
    def temp_size(self) -> int:
        return sum(f.size for f in self.temp_files)


@dataclass
class MoveAction:
    source: Path
    destination: Path
    file_size: int
    action_type: str = "move"
    status: str = "pending"
    error: Optional[str] = None


@dataclass
class Plan:
    actions: List[MoveAction] = field(default_factory=list)
    categories: Dict[str, List[MoveAction]] = field(default_factory=dict)

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    @property
    def total_size(self) -> int:
        return sum(a.file_size for a in self.actions)


@dataclass
class MoveLog:
    timestamp: datetime
    actions: List[MoveAction] = field(default_factory=list)
    log_id: str = ""
    source: str = "direct"
    plan_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "plan_id": self.plan_id,
            "actions": [
                {
                    "source": str(a.source),
                    "destination": str(a.destination),
                    "file_size": a.file_size,
                    "status": a.status,
                }
                for a in self.actions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MoveLog":
        return cls(
            log_id=data["log_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source", "direct"),
            plan_id=data.get("plan_id"),
            actions=[
                MoveAction(
                    source=Path(a["source"]),
                    destination=Path(a["destination"]),
                    file_size=a["file_size"],
                    status=a["status"],
                )
                for a in data["actions"]
            ],
        )


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"
