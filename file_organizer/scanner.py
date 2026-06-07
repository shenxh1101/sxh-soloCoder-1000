import os
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable
from collections import defaultdict

from .models import FileInfo, ScanResult, DuplicateGroup, format_size
from .config import DEFAULT_EXCLUDE_DIRS, match_name_pattern
from .rule_manager import RuleSet


class Scanner:
    def __init__(
        self,
        root_dir: Path,
        exclude_dirs: Optional[List[str]] = None,
        min_size: int = 0,
        max_size: int = -1,
        file_types: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        name_pattern: Optional[str] = None,
        detect_duplicates: bool = True,
        detect_empty: bool = True,
        detect_temp: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        rules: Optional[RuleSet] = None,
    ):
        self.root_dir = Path(root_dir)
        self.rules = rules
        self.exclude_dirs = exclude_dirs or (rules.exclude_dirs if rules else DEFAULT_EXCLUDE_DIRS)
        self.min_size = min_size
        self.max_size = max_size
        self.file_types = file_types
        self.date_from = date_from
        self.date_to = date_to
        self.name_pattern = name_pattern
        self.detect_duplicates = detect_duplicates
        self.detect_empty = detect_empty
        self.detect_temp = detect_temp
        self.progress_callback = progress_callback

    def scan(self) -> ScanResult:
        result = ScanResult()
        all_files: List[Path] = []

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [
                d for d in dirnames
                if d not in self.exclude_dirs
                and not self._is_excluded_path(Path(dirpath) / d)
            ]

            for filename in filenames:
                filepath = Path(dirpath) / filename
                if self._is_excluded_path(filepath):
                    result.excluded.append(filepath)
                    continue
                all_files.append(filepath)

        total_files = len(all_files)
        processed = 0
        size_hash_map: dict = defaultdict(list)

        for filepath in all_files:
            try:
                file_info = self._get_file_info(filepath)
                if file_info and self._passes_filters(file_info):
                    result.files.append(file_info)

                    if self.detect_temp and file_info.is_temporary:
                        result.temp_files.append(file_info)

                    if self.detect_duplicates and file_info.size > 0:
                        size_hash_map[file_info.size].append(file_info)
            except (PermissionError, OSError):
                pass

            processed += 1
            if self.progress_callback:
                self.progress_callback(processed, total_files)

        if self.detect_duplicates:
            result.duplicates = self._detect_duplicates(size_hash_map)
            for dup_group in result.duplicates:
                for f in dup_group.files:
                    f.file_hash = dup_group.file_hash

        if self.detect_empty:
            result.empty_dirs = self._find_empty_dirs()

        return result

    def _get_file_info(self, filepath: Path) -> Optional[FileInfo]:
        try:
            stat = filepath.stat()
            ext = filepath.suffix.lower()

            if self.rules:
                is_temp = self.rules.is_temporary_file(filepath.name)
                classification = self.rules.classify(filepath.name, ext)
                category = classification["category"]
            else:
                from .config import is_temporary_file, get_category_by_extension, get_category_by_name
                is_temp = is_temporary_file(filepath.name)
                name_category = get_category_by_name(filepath.name)
                ext_category = get_category_by_extension(ext)
                category = name_category or ext_category or "other"

            file_type = category

            return FileInfo(
                path=filepath,
                size=stat.st_size,
                created=datetime.fromtimestamp(stat.st_ctime),
                modified=datetime.fromtimestamp(stat.st_mtime),
                extension=ext,
                file_type=file_type,
                is_temporary=is_temp,
                category=category,
            )
        except (PermissionError, OSError, FileNotFoundError):
            return None

    def _passes_filters(self, file_info: FileInfo) -> bool:
        if self.min_size > 0 and file_info.size < self.min_size:
            return False

        if self.max_size > 0 and file_info.size > self.max_size:
            return False

        if self.file_types:
            if file_info.extension.lower() not in [t.lower() for t in self.file_types]:
                return False

        if self.date_from and file_info.modified < self.date_from:
            return False

        if self.date_to and file_info.modified > self.date_to:
            return False

        if self.name_pattern:
            if not match_name_pattern(file_info.name, [self.name_pattern]):
                return False

        return True

    def _is_excluded_path(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            for exclude in self.exclude_dirs:
                if exclude in str(resolved):
                    return True
        except (PermissionError, OSError):
            return True
        return False

    def _detect_duplicates(self, size_hash_map: dict) -> List[DuplicateGroup]:
        duplicates: List[DuplicateGroup] = []
        hash_map: dict = defaultdict(list)

        for size, files in size_hash_map.items():
            if len(files) < 2:
                continue

            for file_info in files:
                try:
                    file_hash = self._calculate_hash(file_info.path)
                    if file_hash:
                        hash_map[file_hash].append(file_info)
                except (PermissionError, OSError):
                    continue

        for file_hash, files in hash_map.items():
            if len(files) >= 2:
                files.sort(key=lambda f: f.modified)
                duplicates.append(DuplicateGroup(file_hash=file_hash, files=files))

        duplicates.sort(key=lambda d: d.wasted_size, reverse=True)
        return duplicates

    def _calculate_hash(self, filepath: Path, chunk_size: int = 65536) -> Optional[str]:
        try:
            hasher = hashlib.md5()
            with open(filepath, "rb") as f:
                chunk = f.read(chunk_size)
                while chunk:
                    hasher.update(chunk)
                    chunk = f.read(chunk_size)
            return hasher.hexdigest()
        except (PermissionError, OSError):
            return None

    def _find_empty_dirs(self) -> List[Path]:
        empty_dirs: List[Path] = []

        for dirpath, dirnames, filenames in os.walk(self.root_dir, topdown=False):
            dirnames[:] = [
                d for d in dirnames
                if d not in self.exclude_dirs
            ]

            dirpath_obj = Path(dirpath)
            if dirpath_obj == self.root_dir:
                continue

            try:
                if not any(dirpath_obj.iterdir()):
                    empty_dirs.append(dirpath_obj)
            except (PermissionError, OSError):
                continue

        return empty_dirs

    def print_summary(self, result: ScanResult) -> None:
        print(f"\n{'='*60}")
        print(f"扫描目录: {self.root_dir}")
        print(f"{'='*60}")
        print(f"文件总数: {result.total_count}")
        print(f"总大小: {format_size(result.total_size)}")
        print(f"-" * 60)

        type_stats: dict = defaultdict(int)
        type_count: dict = defaultdict(int)
        for f in result.files:
            type_stats[f.file_type] += f.size
            type_count[f.file_type] += 1

        print("\n按类型分布:")
        for ftype in sorted(type_stats.keys(), key=lambda t: type_stats[t], reverse=True):
            print(f"  {ftype:15} {type_count[ftype]:5} 个  {format_size(type_stats[ftype])}")

        if result.duplicates:
            print(f"\n重复文件 ({len(result.duplicates)} 组):")
            for i, dup in enumerate(result.duplicates[:10], 1):
                print(f"  {i}. {dup.files[0].name}")
                print(f"     {len(dup.files)} 个副本, 浪费 {format_size(dup.wasted_size)}")
            if len(result.duplicates) > 10:
                print(f"     ... 还有 {len(result.duplicates) - 10} 组")

        if result.temp_files:
            print(f"\n临时文件 ({len(result.temp_files)} 个):")
            print(f"  总大小: {format_size(result.temp_size)}")
            for f in result.temp_files[:10]:
                print(f"  - {f.name} ({format_size(f.size)})")
            if len(result.temp_files) > 10:
                print(f"  ... 还有 {len(result.temp_files) - 10} 个")

        if result.empty_dirs:
            print(f"\n空文件夹 ({len(result.empty_dirs)} 个):")
            for d in result.empty_dirs[:10]:
                print(f"  - {d}")
            if len(result.empty_dirs) > 10:
                print(f"  ... 还有 {len(result.empty_dirs) - 10} 个")

        print(f"\n{'='*60}")
        print(f"可回收空间: {format_size(result.duplicates_size + result.temp_size)}")
        print(f"{'='*60}\n")
