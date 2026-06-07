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

    def to_dict(self) -> dict:
        return {
            "files": [
                {
                    "path": str(f.path),
                    "size": f.size,
                    "created": f.created.isoformat(),
                    "modified": f.modified.isoformat(),
                    "extension": f.extension,
                    "file_type": f.file_type,
                    "is_temporary": f.is_temporary,
                    "file_hash": f.file_hash,
                    "category": f.category,
                }
                for f in self.files
            ],
            "empty_dirs": [str(d) for d in self.empty_dirs],
            "duplicates": [
                {
                    "file_hash": d.file_hash,
                    "files": [
                        {
                            "path": str(f.path),
                            "size": f.size,
                            "created": f.created.isoformat(),
                            "modified": f.modified.isoformat(),
                            "extension": f.extension,
                            "file_type": f.file_type,
                            "is_temporary": f.is_temporary,
                            "file_hash": f.file_hash,
                            "category": f.category,
                        }
                        for f in d.files
                    ],
                }
                for d in self.duplicates
            ],
            "temp_files": [
                {
                    "path": str(f.path),
                    "size": f.size,
                    "created": f.created.isoformat(),
                    "modified": f.modified.isoformat(),
                    "extension": f.extension,
                    "file_type": f.file_type,
                    "is_temporary": f.is_temporary,
                    "file_hash": f.file_hash,
                    "category": f.category,
                }
                for f in self.temp_files
            ],
            "excluded": [str(d) for d in self.excluded],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScanResult":
        files = [
            FileInfo(
                path=Path(f["path"]),
                size=f["size"],
                created=datetime.fromisoformat(f["created"]),
                modified=datetime.fromisoformat(f["modified"]),
                extension=f["extension"],
                file_type=f.get("file_type", "other"),
                is_temporary=f.get("is_temporary", False),
                file_hash=f.get("file_hash"),
                category=f.get("category", "uncategorized"),
            )
            for f in data.get("files", [])
        ]

        duplicates = [
            DuplicateGroup(
                file_hash=d["file_hash"],
                files=[
                    FileInfo(
                        path=Path(f["path"]),
                        size=f["size"],
                        created=datetime.fromisoformat(f["created"]),
                        modified=datetime.fromisoformat(f["modified"]),
                        extension=f["extension"],
                        file_type=f.get("file_type", "other"),
                        is_temporary=f.get("is_temporary", False),
                        file_hash=f.get("file_hash"),
                        category=f.get("category", "uncategorized"),
                    )
                    for f in d["files"]
                ],
            )
            for d in data.get("duplicates", [])
        ]

        temp_files = [
            FileInfo(
                path=Path(f["path"]),
                size=f["size"],
                created=datetime.fromisoformat(f["created"]),
                modified=datetime.fromisoformat(f["modified"]),
                extension=f["extension"],
                file_type=f.get("file_type", "other"),
                is_temporary=f.get("is_temporary", False),
                file_hash=f.get("file_hash"),
                category=f.get("category", "uncategorized"),
            )
            for f in data.get("temp_files", [])
        ]

        return cls(
            files=files,
            empty_dirs=[Path(d) for d in data.get("empty_dirs", [])],
            duplicates=duplicates,
            temp_files=temp_files,
            excluded=[Path(d) for d in data.get("excluded", [])],
        )


@dataclass
class MoveAction:
    source: Path
    destination: Path
    file_size: int
    action_type: str = "move"
    status: str = "pending"
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    category: Optional[str] = None


@dataclass
class Plan:
    actions: List[MoveAction] = field(default_factory=list)
    categories: Dict[str, List[MoveAction]] = field(default_factory=dict)

    @property
    def total_actions(self) -> int:
        return sum(1 for a in self.actions if a.status != "skipped")

    @property
    def total_size(self) -> int:
        return sum(a.file_size for a in self.actions if a.status != "skipped")

    @property
    def skipped_actions(self) -> List[MoveAction]:
        return [a for a in self.actions if a.status == "skipped"]

    @property
    def active_actions(self) -> List[MoveAction]:
        return [a for a in self.actions if a.status != "skipped"]


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
                    "error": a.error,
                    "skip_reason": a.skip_reason,
                    "category": a.category,
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
                    status=a.get("status", "pending"),
                    error=a.get("error"),
                    skip_reason=a.get("skip_reason"),
                    category=a.get("category"),
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
