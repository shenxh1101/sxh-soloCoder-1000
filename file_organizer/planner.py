import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable
from collections import defaultdict

from .models import FileInfo, ScanResult, MoveAction, Plan, format_size
from .config import DEFAULT_CATEGORIES, get_target_dir
from .rule_manager import RuleSet


class PlanGenerator:
    def __init__(
        self,
        scan_result: ScanResult,
        target_root: Path,
        organize_by: str = "category",
        date_format: str = "%Y-%m",
        custom_rules: Optional[Dict] = None,
        rename_pattern: Optional[str] = None,
        exclude_categories: Optional[List[str]] = None,
        include_temp: bool = False,
        dry_run: bool = True,
        rules: Optional[RuleSet] = None,
    ):
        self.scan_result = scan_result
        self.target_root = Path(target_root)
        self.organize_by = organize_by
        self.date_format = date_format
        self.custom_rules = custom_rules or {}
        self.rename_pattern = rename_pattern
        self.exclude_categories = exclude_categories or []
        self.include_temp = include_temp
        self.dry_run = dry_run
        self.rules = rules
        self._existing_files: set = set()
        self._init_existing_files()

    def _init_existing_files(self):
        if not self.target_root.exists():
            return
        for f in self.target_root.rglob("*"):
            if f.is_file():
                try:
                    self._existing_files.add(f.resolve())
                except (PermissionError, OSError):
                    pass

    def generate(self) -> Plan:
        plan = Plan()
        target_tracker: Dict[Path, int] = defaultdict(int)

        for file_info in self.scan_result.files:
            if file_info.category in self.exclude_categories:
                continue

            if file_info.is_temporary and not self.include_temp:
                continue

            target_path = self._get_target_path(file_info)
            if target_path is None:
                continue

            target_path = self._resolve_conflict(target_path, target_tracker)

            if file_info.path.resolve() == target_path.resolve():
                continue

            action = MoveAction(
                source=file_info.path,
                destination=target_path,
                file_size=file_info.size,
            )
            plan.actions.append(action)

            category = file_info.category
            if category not in plan.categories:
                plan.categories[category] = []
            plan.categories[category].append(action)

        plan.actions.sort(key=lambda a: a.destination)
        return plan

    def _get_target_path(self, file_info: FileInfo) -> Optional[Path]:
        target_subdir = self._get_target_subdir(file_info)
        filename = self._get_target_filename(file_info)
        if not filename:
            return None
        return self.target_root / target_subdir / filename

    def _get_target_subdir(self, file_info: FileInfo) -> Path:
        category = file_info.category

        if category in self.custom_rules and "target_dir" in self.custom_rules[category]:
            base_dir = self.custom_rules[category]["target_dir"]
        elif self.rules:
            base_dir = self.rules.get_target_dir(category)
        else:
            base_dir = get_target_dir(category)

        if self.organize_by == "category":
            return Path(base_dir)
        elif self.organize_by == "date":
            date_str = file_info.modified.strftime(self.date_format)
            return Path(base_dir) / date_str
        elif self.organize_by == "category_date":
            date_str = file_info.modified.strftime(self.date_format)
            return Path(base_dir) / date_str
        elif self.organize_by == "date_category":
            date_str = file_info.modified.strftime(self.date_format)
            return Path(date_str) / base_dir
        elif self.organize_by == "extension":
            ext = file_info.extension.lstrip(".").lower() or "no_ext"
            return Path(base_dir) / ext
        else:
            return Path(base_dir)

    def _get_target_filename(self, file_info: FileInfo) -> Optional[str]:
        if not self.rename_pattern:
            return file_info.name

        try:
            filename = self.rename_pattern
            filename = filename.replace("{name}", file_info.path.stem)
            filename = filename.replace("{ext}", file_info.extension.lstrip("."))
            filename = filename.replace("{date}", file_info.modified.strftime("%Y%m%d"))
            filename = filename.replace("{time}", file_info.modified.strftime("%H%M%S"))
            filename = filename.replace("{datetime}", file_info.modified.strftime("%Y%m%d_%H%M%S"))
            filename = filename.replace("{size}", str(file_info.size))
            filename = filename.replace("{category}", file_info.category)

            if file_info.extension and not filename.endswith(file_info.extension):
                filename += file_info.extension

            return filename
        except Exception:
            return file_info.name

    def _resolve_conflict(
        self,
        target_path: Path,
        target_tracker: Dict[Path, int],
    ) -> Path:
        original_path = target_path
        counter = 1

        while self._file_exists(target_path, target_tracker):
            stem = original_path.stem
            suffix = original_path.suffix
            target_path = original_path.with_name(f"{stem}_{counter}{suffix}")
            counter += 1

        target_tracker[target_path.resolve()] += 1
        return target_path

    def _file_exists(self, path: Path, target_tracker: Dict[Path, int]) -> bool:
        try:
            resolved = path.resolve()
            if target_tracker.get(resolved, 0) > 0:
                return True
            if resolved in self._existing_files:
                return True
            return path.exists()
        except (PermissionError, OSError):
            return False

    def print_plan(self, plan: Plan, show_details: bool = False) -> None:
        print(f"\n{'='*70}")
        print(f"整理计划")
        print(f"{'='*70}")
        print(f"目标目录: {self.target_root}")
        print(f"整理方式: {self.organize_by}")
        print(f"待移动文件: {plan.total_actions} 个")
        print(f"总大小: {format_size(plan.total_size)}")
        print(f"{'-'*70}")

        print(f"\n按分类统计:")
        for category in sorted(plan.categories.keys(), key=lambda c: len(plan.categories[c]), reverse=True):
            actions = plan.categories[category]
            cat_size = sum(a.file_size for a in actions)
            cat_name = DEFAULT_CATEGORIES.get(category, {}).get("name", category)
            print(f"  {cat_name:15} {len(actions):5} 个  {format_size(cat_size)}")

        if show_details and plan.actions:
            print(f"\n详细计划:")
            for i, action in enumerate(plan.actions, 1):
                src = action.source
                dst = action.destination
                try:
                    rel_src = src.relative_to(self.scan_result.files[0].path.parents[2])
                except (ValueError, IndexError):
                    rel_src = src.name
                try:
                    rel_dst = dst.relative_to(self.target_root)
                except ValueError:
                    rel_dst = dst

                arrow = "->" if src.name == dst.name else "=>"
                print(f"  {i:4d}. {rel_src}")
                print(f"        {arrow} {rel_dst}")

        print(f"\n{'='*70}\n")

    def export_plan(self, plan: Plan, output_path: Path, filter_excluded: Optional[List[Dict]] = None) -> None:
        from typing import Dict, List, Optional
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# 文件整理计划\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"目标目录: {self.target_root}\n")
            f.write(f"整理方式: {self.organize_by}\n")
            f.write(f"文件总数: {plan.total_actions}\n")
            f.write(f"总大小: {format_size(plan.total_size)}\n\n")

            f.write("## 按分类统计\n\n")
            for category in sorted(plan.categories.keys()):
                actions = plan.categories[category]
                cat_size = sum(a.file_size for a in actions)
                cat_name = DEFAULT_CATEGORIES.get(category, {}).get("name", category)
                f.write(f"- {cat_name}: {len(actions)} 个, {format_size(cat_size)}\n")

            if filter_excluded:
                f.write(f"\n## 筛选排除的文件 ({len(filter_excluded)} 个)\n\n")
                f.write("| 序号 | 文件名 | 分类 | 排除原因 |\n")
                f.write("|------|--------|------|----------|\n")
                for i, item in enumerate(filter_excluded[:50], 1):
                    f.write(f"| {i} | {item.get('filename', '')} | {item.get('category', '')} | {item.get('exclude_reason', '')} |\n")
                if len(filter_excluded) > 50:
                    f.write(f"| ... | 还有 {len(filter_excluded) - 50} 个 | | |\n")
                f.write("\n")

            f.write("## 详细计划\n\n")
            f.write("| 序号 | 源文件 | 目标文件 | 大小 |\n")
            f.write("|------|--------|----------|------|\n")
            for i, action in enumerate(plan.actions, 1):
                f.write(f"| {i} | {action.source.name} | {action.destination.name} | {format_size(action.file_size)} |\n")

        print(f"计划已导出到: {output_path}")
