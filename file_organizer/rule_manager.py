import json
import re
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Pattern
from dataclasses import dataclass, field

import click

from .config import DEFAULT_CATEGORIES, TEMP_PATTERNS, DEFAULT_EXCLUDE_DIRS


try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class RuleConflict:
    type: str
    category: str
    key: str
    builtin_value: str
    user_value: str
    resolved: str
    resolution: str


@dataclass
class RuleSet:
    categories: Dict[str, Dict] = field(default_factory=dict)
    temp_patterns: List[Pattern] = field(default_factory=list)
    exclude_dirs: List[str] = field(default_factory=list)
    conflicts: List[RuleConflict] = field(default_factory=list)
    source_file: Optional[Path] = None
    _temp_pattern_sources: Dict[str, str] = field(default_factory=dict)
    _exclude_dir_sources: Dict[str, str] = field(default_factory=dict)

    def get_category_by_extension(self, ext: str) -> str:
        ext_lower = ext.lower()
        for category, config in self.categories.items():
            if "extensions" in config and ext_lower in config["extensions"]:
                return category
        return "other"

    def get_category_by_name(self, filename: str) -> str:
        for category, config in self.categories.items():
            if "regex_patterns" in config:
                for pattern in config["regex_patterns"]:
                    if re.match(pattern, filename, re.IGNORECASE):
                        return category
            if "patterns" in config:
                for pattern in config["patterns"]:
                    if fnmatch.fnmatch(filename, pattern):
                        return category
        return ""

    def get_target_dir(self, category: str) -> str:
        if category in self.categories and "target_dir" in self.categories[category]:
            return self.categories[category]["target_dir"]
        return "Other"

    def is_temporary_file(self, filename: str) -> bool:
        return any(pattern.match(filename) for pattern in self.temp_patterns)

    def is_excluded_dir(self, dirname: str) -> bool:
        return dirname in self.exclude_dirs


class RuleManager:
    def __init__(self):
        self.default_rules = self._load_default_rules()

    def _load_default_rules(self) -> RuleSet:
        default_temp_sources = {p.pattern: "builtin" for p in TEMP_PATTERNS}
        default_exclude_sources = {d: "builtin" for d in DEFAULT_EXCLUDE_DIRS}

        categories_with_source = {}
        for key, config in DEFAULT_CATEGORIES.items():
            categories_with_source[key] = config.copy()
            categories_with_source[key]["source"] = "builtin"

        return RuleSet(
            categories=categories_with_source,
            temp_patterns=TEMP_PATTERNS.copy(),
            exclude_dirs=DEFAULT_EXCLUDE_DIRS.copy(),
            _temp_pattern_sources=default_temp_sources,
            _exclude_dir_sources=default_exclude_sources,
        )

    def load_config(self, config_path: Optional[Path] = None) -> RuleSet:
        if not config_path:
            return self.default_rules

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        config_data = self._parse_config_file(config_path)
        return self._merge_rules(config_data, config_path)

    def _parse_config_file(self, config_path: Path) -> dict:
        ext = config_path.suffix.lower()

        with open(config_path, "r", encoding="utf-8") as f:
            if ext in (".yaml", ".yml"):
                if not YAML_AVAILABLE:
                    raise ImportError(
                        "需要 PyYAML 库来解析 YAML 文件。请运行: pip install pyyaml"
                    )
                return yaml.safe_load(f)
            elif ext == ".json":
                return json.load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {ext}，支持 .json, .yaml, .yml")

    def _merge_rules(self, user_config: dict, config_path: Path) -> RuleSet:
        merged_categories = {}
        for key, config in self.default_rules.categories.items():
            merged_categories[key] = config.copy()

        merged = RuleSet(
            categories=merged_categories,
            temp_patterns=self.default_rules.temp_patterns.copy(),
            exclude_dirs=self.default_rules.exclude_dirs.copy(),
            source_file=config_path,
            _temp_pattern_sources=self.default_rules._temp_pattern_sources.copy(),
            _exclude_dir_sources=self.default_rules._exclude_dir_sources.copy(),
        )

        if "categories" in user_config:
            self._merge_categories(merged, user_config["categories"])

        if "temp_patterns" in user_config:
            self._merge_temp_patterns(merged, user_config["temp_patterns"])

        if "exclude_dirs" in user_config:
            self._merge_exclude_dirs(merged, user_config["exclude_dirs"])

        return merged

    def _merge_categories(self, merged: RuleSet, user_categories: dict):
        for cat_key, cat_config in user_categories.items():
            if cat_key not in merged.categories:
                new_config = cat_config.copy()
                new_config["source"] = "user"
                merged.categories[cat_key] = new_config
                continue

            builtin_config = merged.categories[cat_key]

            if "target_dir" in cat_config and cat_config["target_dir"] != builtin_config.get("target_dir"):
                merged.conflicts.append(RuleConflict(
                    type="category_target_dir",
                    category=cat_key,
                    key="target_dir",
                    builtin_value=builtin_config.get("target_dir", ""),
                    user_value=cat_config["target_dir"],
                    resolved=cat_config["target_dir"],
                    resolution="用户配置覆盖内置配置",
                ))
                builtin_config["target_dir"] = cat_config["target_dir"]

            if "extensions" in cat_config:
                builtin_exts = set(builtin_config.get("extensions", []))
                user_exts = set(cat_config["extensions"])
                common_exts = builtin_exts & user_exts

                for ext in common_exts:
                    for other_cat, other_config in merged.categories.items():
                        if other_cat != cat_key and ext in other_config.get("extensions", []):
                            merged.conflicts.append(RuleConflict(
                                type="extension_conflict",
                                category=cat_key,
                                key=f"extension:{ext}",
                                builtin_value=f"属于 {other_cat}",
                                user_value=f"属于 {cat_key}",
                                resolved=cat_key,
                                resolution="用户配置优先，移至用户指定分类",
                            ))
                            other_config["extensions"] = [
                                e for e in other_config.get("extensions", []) if e != ext
                            ]

                if common_exts:
                    merged.conflicts.append(RuleConflict(
                        type="extension_overlap",
                        category=cat_key,
                        key="extensions",
                        builtin_value=str(builtin_exts),
                        user_value=str(user_exts),
                        resolved=str(builtin_exts | user_exts),
                        resolution="合并扩展名列表",
                    ))

                builtin_config["extensions"] = list(builtin_exts | user_exts)

            if "patterns" in cat_config:
                if "patterns" in builtin_config:
                    builtin_patterns = set(builtin_config["patterns"])
                    user_patterns = set(cat_config["patterns"])
                    common_patterns = builtin_patterns & user_patterns

                    if common_patterns:
                        merged.conflicts.append(RuleConflict(
                            type="pattern_overlap",
                            category=cat_key,
                            key="patterns",
                            builtin_value=str(builtin_patterns),
                            user_value=str(user_patterns),
                            resolved=str(builtin_patterns | user_patterns),
                            resolution="合并命名模式列表(glob)",
                        ))

                    builtin_config["patterns"] = list(builtin_patterns | user_patterns)
                else:
                    builtin_config["patterns"] = cat_config["patterns"]

            if "regex_patterns" in cat_config:
                if "regex_patterns" in builtin_config:
                    builtin_patterns = set(builtin_config["regex_patterns"])
                    user_patterns = set(cat_config["regex_patterns"])
                    common_patterns = builtin_patterns & user_patterns

                    if common_patterns:
                        merged.conflicts.append(RuleConflict(
                            type="regex_pattern_overlap",
                            category=cat_key,
                            key="regex_patterns",
                            builtin_value=str(builtin_patterns),
                            user_value=str(user_patterns),
                            resolved=str(builtin_patterns | user_patterns),
                            resolution="合并正则模式列表",
                        ))

                    builtin_config["regex_patterns"] = list(builtin_patterns | user_patterns)
                else:
                    builtin_config["regex_patterns"] = cat_config["regex_patterns"]

            if "name" in cat_config and cat_config["name"] != builtin_config.get("name"):
                builtin_config["name"] = cat_config["name"]

            builtin_config["source"] = "user"

    def _merge_temp_patterns(self, merged: RuleSet, user_patterns: List[str]):
        existing_patterns = {p.pattern for p in merged.temp_patterns}

        for pattern_str in user_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                if pattern.pattern in existing_patterns:
                    merged.conflicts.append(RuleConflict(
                        type="temp_pattern_duplicate",
                        category="temp_files",
                        key=pattern_str,
                        builtin_value=pattern_str,
                        user_value=pattern_str,
                        resolved=pattern_str,
                        resolution="重复规则，保留一个",
                    ))
                    merged._temp_pattern_sources[pattern.pattern] = "user"
                else:
                    merged.temp_patterns.append(pattern)
                    existing_patterns.add(pattern.pattern)
                    merged._temp_pattern_sources[pattern.pattern] = "user"
            except re.error as e:
                raise ValueError(f"无效的正则表达式 '{pattern_str}': {e}")

    def _merge_exclude_dirs(self, merged: RuleSet, user_excludes: List[str]):
        existing = set(merged.exclude_dirs)

        for dirname in user_excludes:
            if dirname in existing:
                merged.conflicts.append(RuleConflict(
                    type="exclude_duplicate",
                    category="exclude_dirs",
                    key=dirname,
                    builtin_value=dirname,
                    user_value=dirname,
                    resolved=dirname,
                    resolution="重复排除目录，保留一个",
                ))
                merged._exclude_dir_sources[dirname] = "user"
            else:
                merged.exclude_dirs.append(dirname)
                existing.add(dirname)
                merged._exclude_dir_sources[dirname] = "user"

    def print_conflicts(self, rules: RuleSet):
        if not rules.conflicts:
            click.echo("[OK] 没有规则冲突")
            return

        click.echo(f"\n[!] 发现 {len(rules.conflicts)} 个规则冲突/合并:")
        click.echo("=" * 70)

        for i, conflict in enumerate(rules.conflicts, 1):
            click.echo(f"\n{i}. 类型: {conflict.type}")
            if conflict.category:
                click.echo(f"   分类: {conflict.category}")
            click.echo(f"   键: {conflict.key}")
            click.echo(f"   内置值: {conflict.builtin_value}")
            click.echo(f"   用户值: {conflict.user_value}")
            click.echo(f"   最终值: {conflict.resolved}")
            click.echo(f"   处理方式: {conflict.resolution}")

        click.echo(f"\n{'='*70}\n")
