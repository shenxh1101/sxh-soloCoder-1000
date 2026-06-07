import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict
import click

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from .scanner import Scanner
from .planner import PlanGenerator
from .mover import FileMover
from .undo import UndoManager
from .reporter import Reporter
from .models import format_size, ScanResult, Plan, MoveLog
from .config import DEFAULT_EXCLUDE_DIRS, DEFAULT_CATEGORIES
from .rule_manager import RuleManager, RuleSet


def parse_size(size_str: str) -> int:
    size_str = size_str.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}
    for unit in ["GB", "MB", "KB", "B"]:
        if size_str.endswith(unit):
            try:
                return int(float(size_str[:-len(unit)]) * units[unit])
            except ValueError:
                raise click.BadParameter(f"无效的大小格式: {size_str}")
    try:
        return int(size_str)
    except ValueError:
        raise click.BadParameter(f"无效的大小格式: {size_str}")


def parse_date(date_str: str, end_of_day: bool = False) -> datetime:
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt
        except ValueError:
            continue
    raise click.BadParameter(f"无效的日期格式: {date_str}")


def progress_scan(current: int, total: int) -> None:
    if total > 0:
        percent = current * 100 // total
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        click.echo(f"\r  扫描进度: [{bar}] {percent}% ({current}/{total})", nl=False)
        if current == total:
            click.echo()


def progress_move(current: int, total: int, action) -> None:
    if total > 0:
        percent = current * 100 // total
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        status = "[OK]" if action.status == "success" else "[SIM]"
        click.echo(f"\r  移动进度: [{bar}] {percent}% ({current}/{total}) {status} {action.source.name}", nl=False)
        if current == total:
            click.echo()


@click.group(help="文件整理工具 - 帮助你整理电脑中杂乱的文件")
@click.version_option(version="1.0.0", prog_name="fileorg")
def cli():
    pass


@cli.command("scan", help="扫描目录，分析文件分布")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--exclude", "-e", multiple=True, help="排除的目录名，可多次指定")
@click.option("--min-size", "min_size_str", default="0B", help="最小文件大小，如 1MB、500KB")
@click.option("--max-size", "max_size_str", default="-1", help="最大文件大小，如 1GB")
@click.option("--type", "file_types", multiple=True, help="按文件扩展名过滤，如 .jpg .pdf")
@click.option("--date-from", help="起始修改日期，格式 YYYY-MM-DD")
@click.option("--date-to", help="结束修改日期，格式 YYYY-MM-DD")
@click.option("--name-pattern", help="文件名匹配的正则表达式")
@click.option("--no-duplicates", is_flag=True, help="不检测重复文件")
@click.option("--no-empty", is_flag=True, help="不检测空文件夹")
@click.option("--no-temp", is_flag=True, help="不检测临时文件")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="导出扫描报告到文件")
@click.option("--output-json", type=click.Path(path_type=Path), help="导出JSON格式扫描报告")
@click.option("--quiet", "-q", is_flag=True, help="静默模式，只输出结果摘要")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="自定义规则配置文件 (JSON/YAML)")
def scan_command(
    directory: Path,
    exclude: Tuple[str, ...],
    min_size_str: str,
    max_size_str: str,
    file_types: Tuple[str, ...],
    date_from: Optional[str],
    date_to: Optional[str],
    name_pattern: Optional[str],
    no_duplicates: bool,
    no_empty: bool,
    no_temp: bool,
    output: Optional[Path],
    output_json: Optional[Path],
    quiet: bool,
    config_path: Optional[Path],
):
    directory = directory.resolve()

    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path and not quiet:
        click.echo(f"[FILE] 加载配置文件: {config_path}")
        rule_manager.print_conflicts(rules)

    exclude_dirs = list(rules.exclude_dirs) + list(exclude)
    min_size = parse_size(min_size_str)
    max_size = parse_size(max_size_str) if max_size_str != "-1" else -1

    dt_from = parse_date(date_from) if date_from else None
    dt_to = parse_date(date_to, end_of_day=True) if date_to else None

    click.echo(f"\n[SCAN] 开始扫描目录: {directory}")
    click.echo("-" * 60)

    scanner = Scanner(
        root_dir=directory,
        exclude_dirs=exclude_dirs,
        min_size=min_size,
        max_size=max_size,
        file_types=list(file_types) if file_types else None,
        date_from=dt_from,
        date_to=dt_to,
        name_pattern=name_pattern,
        detect_duplicates=not no_duplicates,
        rules=rules,
        detect_empty=not no_empty,
        detect_temp=not no_temp,
        progress_callback=None if quiet else progress_scan,
    )

    result = scanner.scan()

    if not quiet:
        scanner.print_summary(result)

    Reporter.print_summary(result)

    if output:
        Reporter.generate_scan_report(result, output)

    if output_json:
        Reporter.generate_scan_report_json(result, output_json)

    scan_cache = Path.home() / ".file_organizer" / "last_scan.json"
    scan_cache.parent.mkdir(parents=True, exist_ok=True)
    scan_data = {
        "directory": str(directory),
        "timestamp": datetime.now().isoformat(),
        "file_count": result.total_count,
        "total_size": result.total_size,
        "config_file": str(config_path) if config_path else None,
    }
    with open(scan_cache, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, ensure_ascii=False, indent=2)


@cli.command("plan", help="生成整理计划（不实际移动文件）")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--target", "-t", type=click.Path(file_okay=False, path_type=Path), required=True, help="整理后的目标目录")
@click.option("--organize-by", type=click.Choice(["category", "date", "category_date", "date_category", "extension"]), default="category", help="整理方式")
@click.option("--date-format", default="%Y-%m", help="日期文件夹格式，默认 %Y-%m")
@click.option("--exclude", "-e", multiple=True, help="排除的目录名")
@click.option("--exclude-category", multiple=True, help="排除的分类，如 images videos")
@click.option("--include-temp", is_flag=True, help="包含临时文件")
@click.option("--rename-pattern", help="批量重命名模式，如 {date}_{name}")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="导出计划到文件")
@click.option("--output-json", type=click.Path(path_type=Path), help="导出JSON格式计划")
@click.option("--detail", "-d", "show_detail", is_flag=True, help="显示详细计划")
@click.option("--no-confirm", is_flag=True, help="跳过交互式确认")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="自定义规则配置文件 (JSON/YAML)")
@click.option("--only-category", multiple=True, help="仅包含指定分类，如 images videos")
@click.option("--skip-pattern", multiple=True, help="跳过匹配关键词模式的文件，如 *Screenshot* *backup*")
@click.option("--skip-regex", multiple=True, help="跳过匹配正则表达式的文件，如 ^test_.* \\.bak$")
def plan_command(
    directory: Path,
    target: Path,
    organize_by: str,
    date_format: str,
    exclude: Tuple[str, ...],
    exclude_category: Tuple[str, ...],
    include_temp: bool,
    rename_pattern: Optional[str],
    output: Optional[Path],
    output_json: Optional[Path],
    show_detail: bool,
    no_confirm: bool,
    config_path: Optional[Path],
    only_category: Tuple[str, ...],
    skip_pattern: Tuple[str, ...],
    skip_regex: Tuple[str, ...],
):
    directory = directory.resolve()
    target = target.resolve()

    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path:
        click.echo(f"[FILE] 加载配置文件: {config_path}")
        rule_manager.print_conflicts(rules)

    click.echo(f"\n[PLAN] 生成整理计划")
    click.echo(f"源目录: {directory}")
    click.echo(f"目标目录: {target}")
    click.echo(f"整理方式: {organize_by}")
    click.echo("-" * 60)

    exclude_dirs = list(rules.exclude_dirs) + list(exclude)

    with click.progressbar(length=1, label="扫描文件") as bar:
        scanner = Scanner(
            root_dir=directory,
            exclude_dirs=exclude_dirs,
            rules=rules,
        )
        result = scanner.scan()
        bar.update(1)

    click.echo(f"  共扫描到 {result.total_count} 个文件")

    planner = PlanGenerator(
        scan_result=result,
        target_root=target,
        organize_by=organize_by,
        date_format=date_format,
        exclude_categories=list(exclude_category),
        include_temp=include_temp,
        rename_pattern=rename_pattern,
        rules=rules,
    )

    plan = planner.generate()
    filter_excluded = []

    if only_category or skip_pattern or skip_regex:
        import fnmatch
        import re

        click.echo(f"\n[FILTER] 应用二次筛选:")
        if only_category:
            click.echo(f"  仅包含分类: {', '.join(only_category)}")
        if skip_pattern:
            click.echo(f"  跳过关键词: {', '.join(skip_pattern)}")
        if skip_regex:
            click.echo(f"  跳过正则: {', '.join(skip_regex)}")

        filtered_actions = []
        filtered_categories = {}

        only_cat_set = set(only_category) if only_category else None
        skip_regex_compiled = [re.compile(p, re.IGNORECASE) for p in skip_regex]

        for action in plan.actions:
            filename = action.source.name
            category = None

            for cat, actions in plan.categories.items():
                if any(a.source == action.source for a in actions):
                    category = cat
                    break

            excluded = False
            exclude_reason = None

            if only_cat_set and category not in only_cat_set:
                excluded = True
                exclude_reason = f"不在白名单分类: {category}"
            else:
                for pattern in skip_pattern:
                    if fnmatch.fnmatch(filename, pattern):
                        excluded = True
                        exclude_reason = f"匹配跳过关键词: {pattern}"
                        break

                if not excluded:
                    for pattern in skip_regex_compiled:
                        if pattern.match(filename):
                            excluded = True
                            exclude_reason = f"匹配跳过正则: {pattern.pattern}"
                            break

            if excluded:
                filter_excluded.append({
                    "source": str(action.source),
                    "filename": filename,
                    "category": category,
                    "file_size": action.file_size,
                    "exclude_reason": exclude_reason,
                })
            else:
                filtered_actions.append(action)

        for cat, actions in plan.categories.items():
            if only_cat_set and cat not in only_cat_set:
                continue

            cat_filtered = []
            for action in actions:
                filename = action.source.name
                excluded = False

                for pattern in skip_pattern:
                    if fnmatch.fnmatch(filename, pattern):
                        excluded = True
                        break

                if not excluded:
                    for pattern in skip_regex_compiled:
                        if pattern.match(filename):
                            excluded = True
                            break

                if not excluded:
                    cat_filtered.append(action)

            if cat_filtered:
                filtered_categories[cat] = cat_filtered

        plan.actions = filtered_actions
        plan.categories = filtered_categories

        click.echo(f"  筛选结果: 保留 {len(plan.actions)} 个, 排除 {len(filter_excluded)} 个")

    planner.print_plan(plan, show_details=show_detail)

    if filter_excluded:
        click.echo(f"\n[INFO] 被筛选排除的文件 ({len(filter_excluded)} 个):")
        for i, item in enumerate(filter_excluded[:10], 1):
            click.echo(f"  {i:2d}. {item['filename']} ({item['exclude_reason']})")
        if len(filter_excluded) > 10:
            click.echo(f"  ... 还有 {len(filter_excluded) - 10} 个")

    skipped_categories: set = set()
    skipped_files: set = set()

    if not no_confirm and plan.total_actions > 0:
        plan, skipped_categories, skipped_files = interactive_plan_confirm(plan, rules)

    plan_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]

    if output:
        planner.export_plan(plan, output, filter_excluded if filter_excluded else None)

    if output_json:
        export_plan_json(plan, output_json, plan_id, skipped_categories, skipped_files, config_path, result, filter_excluded if filter_excluded else None)

    save_confirmed_plan(plan, plan_id, skipped_categories, skipped_files, config_path, directory, result)

    click.echo(f"[SAVE] 计划已保存，ID: {plan_id}")
    click.echo(f"   使用 'move --from-plan' 执行此计划\n")


import uuid


@cli.command("move", help="执行整理，移动文件")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path), required=False)
@click.option("--target", "-t", type=click.Path(file_okay=False, path_type=Path), help="整理后的目标目录")
@click.option("--organize-by", type=click.Choice(["category", "date", "category_date", "date_category", "extension"]), default="category", help="整理方式")
@click.option("--date-format", default="%Y-%m", help="日期文件夹格式")
@click.option("--exclude", "-e", multiple=True, help="排除的目录名")
@click.option("--exclude-category", multiple=True, help="排除的分类")
@click.option("--include-temp", is_flag=True, help="包含临时文件")
@click.option("--rename-pattern", help="批量重命名模式")
@click.option("--simulate", "-s", is_flag=True, help="模拟执行，不实际移动")
@click.option("--yes", "-y", is_flag=True, help="跳过确认")
@click.option("--report", "-r", type=click.Path(path_type=Path), help="导出Markdown格式整理报告")
@click.option("--report-json", type=click.Path(path_type=Path), help="导出JSON格式整理报告")
@click.option("--from-plan", "plan_id", is_flag=True, flag_value="last", help="使用上次生成的计划")
@click.option("--plan-id", help="使用指定ID的计划")
@click.option("--plan-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="从指定JSON文件读取计划（支持手动修改）")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="自定义规则配置文件 (JSON/YAML)")
def move_command(
    directory: Optional[Path],
    target: Optional[Path],
    organize_by: str,
    date_format: str,
    exclude: Tuple[str, ...],
    exclude_category: Tuple[str, ...],
    include_temp: bool,
    rename_pattern: Optional[str],
    simulate: bool,
    yes: bool,
    report: Optional[Path],
    report_json: Optional[Path],
    plan_id: Optional[str],
    plan_file: Optional[Path],
    config_path: Optional[Path],
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)
    result = None
    used_plan_id = None
    plan_data = None

    if plan_file:
        click.echo(f"[FILE] 从外部文件加载计划: {plan_file}")
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        used_plan_id = plan_data.get("plan_id", "external")
        if used_plan_id == "external":
            used_plan_id = f"external_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elif plan_id:
        if plan_id == "last":
            plan_data = load_confirmed_plan()
            if plan_data:
                used_plan_id = plan_data.get("plan_id")
        else:
            plan_data = load_confirmed_plan(plan_id)
            used_plan_id = plan_id

    if plan_data:
        from .models import Plan, MoveAction, ScanResult
        plan = Plan()

        plan_config_path = plan_data.get("config_file")
        if plan_config_path and not config_path:
            click.echo(f"[FILE] 加载计划关联的配置文件: {plan_config_path}")
            rules = rule_manager.load_config(Path(plan_config_path))
            rule_manager.print_conflicts(rules)

        if "scan_result" in plan_data:
            result = ScanResult.from_dict(plan_data["scan_result"])
            click.echo(f"[INFO] 使用计划保存的扫描结果: {result.total_count} 个文件")

        if "skipped" in plan_data:
            skipped_categories_from_plan = set(plan_data["skipped"].get("categories", []))
            skipped_files_from_plan = set(plan_data["skipped"].get("files", []))
        else:
            skipped_categories_from_plan = set(plan_data.get("skipped_categories", []))
            skipped_files_from_plan = set(plan_data.get("skipped_files", []))

        skipped_categories_final = set()
        skipped_files_final = set()

        file_skip_status = {}

        for cat, cat_data in plan_data.get("categories", {}).items():
            if isinstance(cat_data, dict) and "actions" in cat_data:
                category_skipped = cat_data.get("skipped", False)
                actions_data = cat_data["actions"]
            else:
                category_skipped = False
                actions_data = cat_data
            
            if category_skipped:
                skipped_categories_final.add(cat)
            
            for a in actions_data:
                source_str = str(a["source"])
                action_skipped = a.get("skipped", False) or \
                                category_skipped or \
                                source_str in skipped_files_from_plan or \
                                cat in skipped_categories_from_plan
                
                skip_reason = None
                if category_skipped or cat in skipped_categories_from_plan:
                    skip_reason = f"分类跳过: {cat}"
                elif a.get("skipped") or source_str in skipped_files_from_plan:
                    skip_reason = "文件跳过: 用户标记"
                
                if source_str not in file_skip_status:
                    file_skip_status[source_str] = {
                        "skipped": action_skipped,
                        "skip_reason": skip_reason,
                        "category": cat,
                        "action_data": a,
                    }
                else:
                    existing = file_skip_status[source_str]
                    if action_skipped and not existing["skipped"]:
                        existing["skipped"] = True
                        existing["skip_reason"] = skip_reason

        for a in plan_data["actions"]:
            source_str = str(a["source"])
            action_skipped = a.get("skipped", False) or \
                            source_str in skipped_files_from_plan
            
            in_skipped_cat = False
            action_category = a.get("category")
            for cat, cat_data in plan_data.get("categories", {}).items():
                if isinstance(cat_data, dict) and cat_data.get("skipped", False):
                    if any(aa.get("source") == source_str for aa in cat_data.get("actions", [])):
                        in_skipped_cat = True
                        break
            
            skip_reason = None
            if in_skipped_cat:
                skip_reason = f"分类跳过: {action_category or '未知分类'}"
                action_skipped = True
            elif a.get("skipped") or source_str in skipped_files_from_plan:
                skip_reason = "文件跳过: 用户标记"
                action_skipped = True
            
            if not action_category:
                for cat, cat_data in plan_data.get("categories", {}).items():
                    if isinstance(cat_data, dict) and "actions" in cat_data:
                        if any(aa.get("source") == source_str for aa in cat_data.get("actions", [])):
                            action_category = cat
                            break
            
            if source_str not in file_skip_status:
                file_skip_status[source_str] = {
                    "skipped": action_skipped,
                    "skip_reason": skip_reason,
                    "category": action_category,
                    "action_data": a,
                }
            else:
                existing = file_skip_status[source_str]
                if action_skipped and not existing["skipped"]:
                    existing["skipped"] = True
                    existing["skip_reason"] = skip_reason
                if not existing["category"] and action_category:
                    existing["category"] = action_category

        for cat in plan_data.get("categories", {}).keys():
            if cat not in plan.categories:
                plan.categories[cat] = []

        for source_str, info in file_skip_status.items():
            a = info["action_data"]
            cat = info["category"]
            action = MoveAction(
                source=Path(a["source"]),
                destination=Path(a["destination"]),
                file_size=a["file_size"],
                category=cat,
            )
            
            if info["skipped"]:
                action.status = "skipped"
                action.skip_reason = info["skip_reason"]
                skipped_files_final.add(source_str)
            
            if cat and cat in plan.categories:
                plan.categories[cat].append(action)
            
            plan.actions.append(action)

        if plan.actions:
            target = plan.actions[0].destination.parent.parent

        all_category_skipped = skipped_categories_from_plan | skipped_categories_final
        all_file_skipped = skipped_files_from_plan | skipped_files_final

        total_actions = len(plan.actions)
        skipped_count = sum(1 for a in plan.actions if a.status == "skipped")
        move_count = plan.total_actions

        click.echo(f"\n[PLAN] 使用计划 {used_plan_id}")
        click.echo(f"   计划总数: {total_actions} 个文件")
        click.echo(f"   将移动: {move_count} 个文件")
        click.echo(f"   将跳过: {skipped_count} 个文件")
        if all_category_skipped:
            click.echo(f"   跳过分类: {', '.join(sorted(all_category_skipped))}")
        if skipped_files_final:
            click.echo(f"   跳过文件: {len(skipped_files_final)} 个")

        click.echo()
        if not yes:
            confirm = click.confirm(f"确认执行以上计划? (将移动 {move_count} 个文件，跳过 {skipped_count} 个)", default=False)
            if not confirm:
                click.echo("已取消")
                return
    elif plan_id or plan_file:
        if plan_file:
            click.echo("[X] 未从外部文件加载到计划数据")
        elif plan_id == "last":
            click.echo("[X] 未找到确认过的计划，请先运行 plan 命令并完成确认")
        else:
            click.echo(f"[X] 未找到计划 {plan_id}")
        sys.exit(1)
    else:
        if not directory or not target:
            click.echo("[X] 请指定源目录和目标目录，或使用 --from-plan")
            sys.exit(1)

        directory = directory.resolve()
        target = target.resolve()

        if config_path:
            click.echo(f"[FILE] 加载配置文件: {config_path}")
            rule_manager.print_conflicts(rules)

        click.echo(f"\n{'[!]  模拟执行' if simulate else '[GO] 执行整理'}")
        click.echo(f"源目录: {directory}")
        click.echo(f"目标目录: {target}")
        click.echo("-" * 60)

        exclude_dirs = list(rules.exclude_dirs) + list(exclude)

        with click.progressbar(length=1, label="扫描文件") as bar:
            scanner = Scanner(
                root_dir=directory,
                exclude_dirs=exclude_dirs,
                rules=rules,
            )
            result = scanner.scan()
            bar.update(1)

        planner = PlanGenerator(
            scan_result=result,
            target_root=target,
            organize_by=organize_by,
            date_format=date_format,
            exclude_categories=list(exclude_category),
            include_temp=include_temp,
            rename_pattern=rename_pattern,
            rules=rules,
        )

        plan = planner.generate()
        planner.print_plan(plan, show_details=False)

    if plan.total_actions == 0:
        click.echo("没有需要移动的文件")
        
        # 即使没有需要移动的文件，如果指定了报告参数，也生成报告
        if report or report_json:
            from datetime import datetime as dt
            from .models import MoveLog, MoveAction
            empty_log = MoveLog(
                timestamp=dt.now(),
                actions=[],
                source="plan" if used_plan_id else "direct",
                plan_id=used_plan_id,
            )
            # 确定配置文件路径：命令行指定的优先，否则使用计划关联的
            if config_path:
                config_file_str = str(config_path)
            elif plan_data:
                config_file_str = plan_data.get("config_file")
            else:
                config_file_str = None
            
            if report:
                Reporter.generate_organize_report(
                    plan, empty_log, report,
                    scan_result=result,
                    plan_id=used_plan_id,
                    config_file=config_file_str,
                    plan_data=plan_data,
                )
                if result:
                    Reporter.generate_savings_report(result, empty_log, report.with_name(report.stem + "_savings" + report.suffix))
            if report_json:
                Reporter.generate_organize_report_json(
                    plan, empty_log, report_json,
                    scan_result=result,
                    plan_id=used_plan_id,
                    config_file=config_file_str,
                    plan_data=plan_data,
                )
        return

    if not yes:
        click.echo()
        if simulate:
            confirm = click.confirm("确认模拟执行?", default=True)
        else:
            confirm = click.confirm(f"确认移动 {plan.total_actions} 个文件? 此操作可以通过 undo 回滚", default=False)
        if not confirm:
            click.echo("已取消")
            return

    mover = FileMover(
        plan=plan,
        progress_callback=progress_move,
    )

    execute_source = "plan" if used_plan_id else "direct"
    log = mover.execute(simulate=simulate, source=execute_source, plan_id=used_plan_id)
    FileMover.print_execution_summary(log, simulate=simulate)

    # 确定配置文件路径：命令行指定的优先，否则使用计划关联的
    if config_path:
        config_file_str = str(config_path)
    elif plan_data:
        config_file_str = plan_data.get("config_file")
    else:
        config_file_str = None
        
    if report or report_json:
        if report:
            Reporter.generate_organize_report(
                plan, log, report,
                scan_result=result,
                plan_id=used_plan_id,
                config_file=config_file_str,
                plan_data=plan_data,
            )
            if result:
                Reporter.generate_savings_report(result, log, report.with_name(report.stem + "_savings" + report.suffix))

        if report_json:
            Reporter.generate_organize_report_json(
                plan, log, report_json,
                scan_result=result,
                plan_id=used_plan_id,
                config_file=config_file_str,
                plan_data=plan_data,
            )


@cli.command("undo", help="回滚上次整理操作")
@click.option("--log-id", help="指定要回滚的日志ID，不指定则回滚最近一次")
@click.option("--simulate", "-s", is_flag=True, help="模拟回滚")
@click.option("--history", "-h", is_flag=True, help="显示操作历史")
@click.option("--detail", "-d", help="显示指定日志的详细信息")
@click.option("--yes", "-y", is_flag=True, help="跳过确认")
def undo_command(
    log_id: Optional[str],
    simulate: bool,
    history: bool,
    detail: Optional[str],
    yes: bool,
):
    undo_manager = UndoManager()

    if history:
        undo_manager.list_history()
        return

    if detail:
        undo_manager.show_log_details(detail)
        return

    if not log_id:
        logs = FileMover.list_logs(limit=1)
        if not logs:
            click.echo("[X] 没有可回滚的操作记录")
            return
        log_id = logs[0].log_id
        click.echo(f"将回滚最近一次操作: {log_id}")

    log = FileMover.load_log(log_id)
    if not log:
        click.echo(f"[X] 未找到日志: {log_id}")
        return

    success_count = sum(1 for a in log.actions if a.status == "success")
    if success_count == 0:
        click.echo("此日志没有成功的操作可以回滚")
        return

    click.echo(f"  操作时间: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"  可回滚文件数: {success_count}")
    click.echo()

    if not yes:
        confirm = click.confirm("确认回滚?", default=False)
        if not confirm:
            click.echo("已取消")
            return

    undo_manager.undo(log_id=log_id, simulate=simulate)


@cli.command("config", help="显示和管理配置")
@click.option("--show-categories", is_flag=True, help="显示所有分类规则")
@click.option("--show-excludes", is_flag=True, help="显示默认排除目录")
@click.option("--show-temp-patterns", is_flag=True, help="显示临时文件匹配规则")
@click.option("--show-conflicts", is_flag=True, help="显示规则冲突详情")
@click.option("--explain-extension", "explain_ext", help="查看某个扩展名最终归属的分类")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="加载并显示用户自定义规则")
def config_command(
    show_categories: bool,
    show_excludes: bool,
    show_temp_patterns: bool,
    show_conflicts: bool,
    explain_ext: Optional[str],
    config_path: Optional[Path],
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path:
        click.echo(f"\n[FILE] 加载配置文件: {config_path}")
        rule_manager.print_conflicts(rules)

    if explain_ext:
        ext = explain_ext.lower()
        if not ext.startswith('.'):
            ext = '.' + ext
        explanation = rules.explain_extension(ext)
        click.echo(f"\n[INFO] 扩展名 {ext} 最终归属:")
        click.echo("=" * 70)
        click.echo(f"  最终分类: {explanation['final_category']}")
        final_cat_name = rules.categories.get(explanation['final_category'], {}).get('name', explanation['final_category'])
        click.echo(f"  分类名称: {final_cat_name}")
        click.echo(f"  规则来源: {'用户配置' if explanation['final_source'] == 'user' else '内置规则'}")
        click.echo(f"  目标目录: {explanation['target_dir']}")
        
        if explanation['conflict']:
            click.echo(f"\n[!] 规则冲突:")
            builtin_cat_name = rules.categories.get(explanation['builtin_category'], {}).get('name', explanation['builtin_category'])
            user_cat_name = rules.categories.get(explanation['user_category'], {}).get('name', explanation['user_category'])
            click.echo(f"  内置分类: {explanation['builtin_category']} ({builtin_cat_name})")
            click.echo(f"  用户分类: {explanation['user_category']} ({user_cat_name})")
            click.echo(f"  处理方式: 用户配置优先，最终归为 {explanation['user_category']}")
        
        if explanation['builtin_category'] and not explanation['user_category']:
            click.echo(f"\n  信息: 此扩展名仅在内置规则中定义")
        
        if explanation['user_category'] and not explanation['builtin_category']:
            click.echo(f"\n  信息: 此扩展名仅在用户配置中定义")
        
        if not explanation['final_category']:
            click.echo(f"\n  信息: 未找到匹配规则，将归类为 other")
        click.echo()
        return

    if show_categories:
        click.echo("\n[CAT] 分类规则")
        click.echo("=" * 60)
        for key, config in rules.categories.items():
            click.echo(f"\n{config.get('name', key)} ({key})")
            click.echo(f"  目标目录: {config.get('target_dir', 'Other')}")
            if "source" in config:
                click.echo(f"  来源: {'用户配置' if config['source'] == 'user' else '内置规则'}")
            if "extensions" in config:
                click.echo(f"  扩展名: {', '.join(config['extensions'])}")
            if "patterns" in config:
                click.echo(f"  命名模式:")
                for p in config["patterns"]:
                    click.echo(f"    - {p}")
            if "regex_patterns" in config:
                click.echo(f"  正则模式:")
                for p in config["regex_patterns"]:
                    click.echo(f"    - {p}")
        click.echo()

    if show_excludes:
        click.echo("\n[EXCLUDE] 排除目录")
        click.echo("=" * 60)
        for d in rules.exclude_dirs:
            source = rules._exclude_dir_sources.get(d, "builtin") if hasattr(rules, '_exclude_dir_sources') else "builtin"
            source_str = " (用户配置)" if source == "user" else " (内置)"
            click.echo(f"  - {d}{source_str}")
        click.echo()

    if show_temp_patterns:
        click.echo("\n[TRASH]  临时文件匹配规则")
        click.echo("=" * 60)
        for p in rules.temp_patterns:
            source = rules._temp_pattern_sources.get(p.pattern, "builtin") if hasattr(rules, '_temp_pattern_sources') else "builtin"
            source_str = " (用户配置)" if source == "user" else " (内置)"
            click.echo(f"  - {p.pattern}{source_str}")
        click.echo()

    if show_conflicts and rules.conflicts:
        rule_manager.print_conflicts(rules)

    if not any([show_categories, show_excludes, show_temp_patterns, show_conflicts]):
        click.echo("\n[CFG]  文件整理工具配置")
        click.echo("=" * 60)
        click.echo(f"分类数量: {len(rules.categories)}")
        click.echo(f"排除目录: {len(rules.exclude_dirs)} 个")
        click.echo(f"临时文件规则: {len(rules.temp_patterns)} 个")
        if rules.conflicts:
            click.echo(f"规则冲突: {len(rules.conflicts)} 个 (使用 --show-conflicts 查看详情)")
        if rules.source_file:
            click.echo(f"配置文件: {rules.source_file}")
        click.echo()
        click.echo("使用以下选项查看详细信息:")
        click.echo("  --show-categories    显示分类规则")
        click.echo("  --show-excludes      显示排除目录")
        click.echo("  --show-temp-patterns 显示临时文件规则")
        click.echo("  --show-conflicts     显示规则冲突详情")
        click.echo("  --config <file>      加载并显示用户自定义规则")
        click.echo()


@cli.command("explain", help="解释文件分类匹配原因")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="自定义规则配置文件 (JSON/YAML)")
@click.option("--output-json", type=click.Path(path_type=Path), help="导出JSON格式解释结果")
@click.option("--show-chain", is_flag=True, help="显示完整匹配链路，包括所有尝试的规则")
def explain_command(
    path: Path,
    config_path: Optional[Path],
    output_json: Optional[Path],
    show_chain: bool,
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path:
        click.echo(f"[FILE] 加载配置文件: {config_path}")

    path = Path(path)

    if path.is_file():
        files_to_explain = [path]
    elif path.is_dir():
        click.echo(f"[SCAN] 扫描目录: {path}")
        exclude_dirs = list(rules.exclude_dirs)
        scanner = Scanner(root_dir=path, exclude_dirs=exclude_dirs, rules=rules)
        result = scanner.scan()
        files_to_explain = [f.path for f in result.files]
        click.echo(f"  共找到 {len(files_to_explain)} 个文件\n")
    else:
        click.echo(f"[X] 路径不存在: {path}")
        sys.exit(1)

    explanations = []
    for file_path in files_to_explain:
        filename = file_path.name
        ext = file_path.suffix.lower() if file_path.suffix else None
        explanation = rules.explain_file(filename, ext)
        explanation["path"] = str(file_path)
        explanations.append(explanation)

    click.echo(f"\n[INFO] 分类匹配解释")
    click.echo("=" * 80)

    match_type_labels = {
        "extension": "扩展名",
        "pattern": "关键词",
        "regex": "正则",
        "default": "默认分类",
    }

    for exp in explanations:
        filename = exp["filename"]
        temp_str = ""
        if exp["is_temporary"]:
            temp_str = f" [临时文件: {exp['temp_pattern']}]"

        source_str = ""
        if exp["category_source"]:
            source_str = f" ({'用户配置' if exp['category_source'] == 'user' else '内置规则'})"

        match_type_str = match_type_labels.get(exp["match_type"], exp["match_type"])

        click.echo(f"\n[FILE] {filename}{temp_str}")
        click.echo(f"   分类: {exp['category']}{source_str}")
        click.echo(f"   目标目录: {exp['target_dir']}")
        click.echo(f"   匹配方式: {match_type_str}")
        click.echo(f"   匹配规则: {exp['match_pattern']}")

        if show_chain:
            click.echo(f"   匹配链路:")
            for i, chain_item in enumerate(exp['match_chain'], 1):
                status = "[OK]" if chain_item['matched'] else "[--]"
                priority = chain_item.get('priority', '')
                source = chain_item.get('source', '')
                source_str = f" ({source})" if source else ""
                priority_str = f" [{priority}]" if priority else ""
                if chain_item['type'] == 'temp_file':
                    click.echo(f"     {i:2d}. {status} 临时文件 {chain_item['pattern']}{source_str}{priority_str}")
                elif chain_item['type'] == 'extension':
                    click.echo(f"     {i:2d}. {status} 扩展名 {chain_item['pattern']} -> {chain_item['category']}{source_str}{priority_str}")
                elif chain_item['type'] == 'regex':
                    click.echo(f"     {i:2d}. {status} 正则 {chain_item['pattern']} -> {chain_item['category']}{source_str}{priority_str}")
                elif chain_item['type'] == 'pattern':
                    click.echo(f"     {i:2d}. {status} 关键词 {chain_item['pattern']} -> {chain_item['category']}{source_str}{priority_str}")
                elif chain_item['type'] == 'default':
                    click.echo(f"     {i:2d}. {status} 默认分类 -> {chain_item['category']}{source_str}{priority_str}")

    if output_json:
        import json
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(explanations, f, ensure_ascii=False, indent=2)
        click.echo(f"\n[SAVE] 解释结果已导出到: {output_path}")


@cli.command("rule-test", help="批量规则调试，测试分类一致性")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="自定义规则配置文件 (JSON/YAML)")
@click.option("--output-json", type=click.Path(path_type=Path), help="导出JSON格式测试结果")
@click.option("--show-inconsistent-only", is_flag=True, help="只显示分类不一致的文件")
@click.option("--filenames", "-f", multiple=True, help="直接指定文件名测试（多个），不扫描目录")
def rule_test_command(
    path: Optional[Path],
    config_path: Optional[Path],
    output_json: Optional[Path],
    show_inconsistent_only: bool,
    filenames: Tuple[str, ...],
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path:
        click.echo(f"[FILE] 加载配置文件: {config_path}")

    match_type_labels = {
        "extension": "扩展名",
        "pattern": "关键词",
        "regex": "正则",
        "default": "默认分类",
    }

    test_files = []

    if filenames:
        click.echo(f"[TEST] 测试指定文件名: {len(filenames)} 个")
        for fn in filenames:
            test_files.append({
                "path": Path(fn),
                "name": fn,
                "ext": Path(fn).suffix.lower() if Path(fn).suffix else None,
            })
    else:
        if not path:
            click.echo(f"[X] 请指定路径或使用 --filenames 参数")
            sys.exit(1)
        path = Path(path)
        if not path.exists():
            click.echo(f"[X] 路径不存在: {path}")
            sys.exit(1)

        if path.is_file():
            test_files.append({
                "path": path,
                "name": path.name,
                "ext": path.suffix.lower() if path.suffix else None,
            })
        elif path.is_dir():
            click.echo(f"[SCAN] 扫描目录: {path}")
            exclude_dirs = list(rules.exclude_dirs)
            scanner = Scanner(root_dir=path, exclude_dirs=exclude_dirs, rules=rules)
            result = scanner.scan()
            click.echo(f"  共找到 {len(result.files)} 个文件\n")

            scan_classifications = {}
            for f in result.files:
                scan_classifications[str(f.path)] = f.category

            for f in result.files:
                test_files.append({
                    "path": f.path,
                    "name": f.name,
                    "ext": f.extension,
                    "scan_category": f.category,
                })

    click.echo(f"\n[INFO] 规则测试结果")
    click.echo("=" * 100)
    click.echo(f"{'文件名':<35} {'分类':<20} {'目标目录':<20} {'匹配方式':<12} {'来源':<10} {'状态':<8}")
    click.echo("-" * 100)

    results = []
    inconsistent_count = 0

    for tf in test_files:
        classification = rules.classify(tf["name"], tf["ext"])
        explanation = rules.explain_file(tf["name"], tf["ext"])

        is_temp = rules.is_temporary_file(tf["name"])
        source = classification.get("category_source", "builtin")
        source_str = "用户" if source == "user" else "内置"

        scan_category = tf.get("scan_category")
        consistent = True
        status_str = "[OK]"
        if scan_category is not None and scan_category != classification["category"]:
            consistent = False
            status_str = "[X]"
            inconsistent_count += 1

        if show_inconsistent_only and consistent:
            continue

        match_type = match_type_labels.get(classification.get("match_type", ""), classification.get("match_type", ""))

        results.append({
            "filename": tf["name"],
            "path": str(tf["path"]),
            "extension": tf["ext"],
            "is_temporary": is_temp,
            "category": classification["category"],
            "category_source": source,
            "match_type": classification.get("match_type"),
            "match_pattern": classification.get("match_pattern"),
            "target_dir": classification.get("target_dir"),
            "scan_category": scan_category,
            "consistent": consistent,
            "match_chain": classification.get("match_chain", []),
        })

        temp_str = " [TEMP]" if is_temp else ""
        click.echo(
            f"{tf['name']:<35} "
            f"{classification['category']:<20} "
            f"{classification.get('target_dir', ''):<20} "
            f"{match_type:<12} "
            f"{source_str:<10} "
            f"{status_str}"
        )
        if not consistent:
            click.echo(f"  {'':>35} -> scan: {scan_category}, explain: {classification['category']}")

    click.echo("=" * 100)
    click.echo(f"[SUMMARY] 测试 {len(test_files)} 个文件, 一致 {len(test_files) - inconsistent_count} 个, 不一致 {inconsistent_count} 个")

    if inconsistent_count > 0:
        click.echo(f"\n[!] 发现 {inconsistent_count} 个文件分类不一致，请检查规则配置")

    if output_json:
        import json
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_files": len(test_files),
                "inconsistent_count": inconsistent_count,
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        click.echo(f"\n[SAVE] 测试结果已导出到: {output_path}")


def interactive_plan_confirm(plan: Plan, rules: RuleSet) -> Tuple[Plan, set, set]:
    skipped_categories: set = set()
    skipped_files: set = set()

    click.echo("\n[?] 交互式计划确认")
    click.echo("=" * 70)
    click.echo("按分类查看计划，可选择跳过整个分类或单个文件")
    click.echo("输入:")
    click.echo("  a - 全部确认")
    click.echo("  q - 跳过剩余全部")
    click.echo("  分类编号 - 查看该分类详情")
    click.echo("=" * 70)

    for i, category in enumerate(sorted(plan.categories.keys()), 1):
        if category in skipped_categories:
            continue
        actions = plan.categories[category]
        cat_name = rules.categories.get(category, {}).get('name',
            DEFAULT_CATEGORIES.get(category, {}).get('name', category))
        cat_size = sum(a.file_size for a in actions)

        click.echo(f"\n{i:2d}. {cat_name:15} [{len(actions):4} 个  {format_size(cat_size)}]")

    while True:
        click.echo()
        choice = click.prompt("\n请选择操作 (a=全部确认, q=跳过全部, 或输入分类编号查看详情)", type=str)
        choice = choice.strip().lower()

        if choice == 'a':
            click.echo("\n[OK] 已确认全部计划")
            break
        elif choice == 'q':
            for cat in plan.categories.keys():
                skipped_categories.add(cat)
            plan.actions = []
            plan.categories = {}
            click.echo("\n[SKIP]  已跳过全部计划")
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            categories = sorted(plan.categories.keys())
            if 0 <= idx < len(categories):
                category = categories[idx]
                actions = plan.categories[category]
                cat_name = rules.categories.get(category, {}).get('name',
                    DEFAULT_CATEGORIES.get(category, {}).get('name', category))

                click.echo(f"\n[CAT] {cat_name} 分类详情:")
                for j, action in enumerate(actions, 1):
                    marker = "[X]" if str(action.source) in skipped_files else "[OK]"
                    click.echo(f"  {j:3d}. [{marker}] {action.source.name} -> {action.destination.relative_to(action.destination.parents[1]) if len(action.destination.parents) >= 2 else action.destination.name}")

                sub_choice = click.prompt("\n操作: s=跳过此分类, 输入编号跳过单个文件, 其他=返回)", type=str)
                if sub_choice.strip().lower() == 's':
                    skipped_categories.add(category)
                    del plan.categories[category]
                    plan.actions = [a for a in plan.actions if a not in actions]
                    click.echo(f"[SKIP]  已跳过分类: {cat_name}")
                elif sub_choice.strip().isdigit():
                    file_idx = int(sub_choice) - 1
                    if 0 <= file_idx < len(actions):
                        action_to_skip = actions[file_idx]
                        skipped_files.add(str(action_to_skip.source))
                        plan.actions.remove(action_to_skip)
                        plan.categories[category].remove(action_to_skip)
                        if not plan.categories[category]:
                            del plan.categories[category]
                        click.echo(f"[SKIP]  已跳过: {action_to_skip.source.name}")
            else:
                click.echo("[X] 无效的分类编号")
        else:
            click.echo("[X] 无效输入")

    remaining = len(plan.actions)
    click.echo(f"\n[NOTE] 最终计划: 保留 {remaining} 个文件")
    return plan, skipped_categories, skipped_files


def save_confirmed_plan(
    plan: Plan,
    plan_id: str,
    skipped_categories: set,
    skipped_files: set,
    config_path: Optional[Path],
    source_directory: Optional[Path] = None,
    scan_result: Optional[ScanResult] = None,
):
    plan_cache = Path.home() / ".file_organizer" / "plans" / f"{plan_id}.json"
    plan_cache.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "plan_id": plan_id,
        "created_at": datetime.now().isoformat(),
        "config_file": str(config_path) if config_path else None,
        "source_directory": str(source_directory) if source_directory else None,
        "skipped_categories": list(skipped_categories),
        "skipped_files": list(skipped_files),
        "actions": [
            {
                "source": str(a.source),
                "destination": str(a.destination),
                "file_size": a.file_size,
                "skipped": False,
            }
            for a in plan.actions
        ],
        "categories": {
            cat: [
                {
                    "source": str(a.source),
                    "destination": str(a.destination),
                    "file_size": a.file_size,
                    "skipped": str(a.source) in skipped_files or cat in skipped_categories,
                }
                for a in actions
            ]
            for cat, actions in plan.categories.items()
        },
    }

    if scan_result:
        data["scan_result"] = scan_result.to_dict()

    with open(plan_cache, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    last_plan_ref = Path.home() / ".file_organizer" / "last_plan_ref.json"
    with open(last_plan_ref, "w", encoding="utf-8") as f:
        json.dump({"last_plan_id": plan_id}, f, ensure_ascii=False, indent=2)


def load_confirmed_plan(plan_id: Optional[str] = None) -> Optional[dict]:
    if plan_id:
        plan_file = Path.home() / ".file_organizer" / "plans" / f"{plan_id}.json"
    else:
        last_ref = Path.home() / ".file_organizer" / "last_plan_ref.json"
        if last_ref.exists():
            with open(last_ref, "r", encoding="utf-8") as f:
                ref_data = json.load(f)
            plan_id = ref_data.get("last_plan_id")
            if plan_id:
                plan_file = Path.home() / ".file_organizer" / "plans" / f"{plan_id}.json"
            else:
                return None
        else:
            return None

    if not plan_file.exists():
        return None

    with open(plan_file, "r", encoding="utf-8") as f:
        return json.load(f)


def export_plan_json(
    plan: Plan,
    output_path: Path,
    plan_id: str,
    skipped_categories: set,
    skipped_files: set,
    config_path: Optional[Path],
    scan_result: Optional[ScanResult] = None,
    filter_excluded: Optional[List[Dict]] = None,
):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "plan_id": plan_id,
        "generated_at": datetime.now().isoformat(),
        "config_file": str(config_path) if config_path else None,
        "summary": {
            "total_actions": plan.total_actions,
            "total_size": plan.total_size,
            "total_size_human": format_size(plan.total_size),
        },
        "skipped_categories": list(skipped_categories),
        "skipped_files": list(skipped_files),
        "actions": [
            {
                "source": str(a.source),
                "destination": str(a.destination),
                "file_size": a.file_size,
                "file_size_human": format_size(a.file_size),
                "skipped": str(a.source) in skipped_files,
            }
            for a in plan.actions
        ],
        "categories": {
            cat: {
                "count": len(actions),
                "size": sum(a.file_size for a in actions),
                "size_human": format_size(sum(a.file_size for a in actions)),
                "skipped": cat in skipped_categories,
                "actions": [
                    {
                        "source": str(a.source),
                        "destination": str(a.destination),
                        "file_size": a.file_size,
                        "file_size_human": format_size(a.file_size),
                        "skipped": str(a.source) in skipped_files or cat in skipped_categories,
                    }
                    for a in actions
                ],
            }
            for cat, actions in plan.categories.items()
        },
    }

    if scan_result:
        data["scan_result"] = scan_result.to_dict()

    if filter_excluded:
        data["filter_excluded"] = filter_excluded
        data["summary"]["filter_excluded_count"] = len(filter_excluded)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    click.echo(f"JSON计划已导出到: {output_path}")


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n\n操作已取消")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n[X] 错误: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
