import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
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
    planner.print_plan(plan, show_details=show_detail)

    skipped_categories: set = set()
    skipped_files: set = set()

    if not no_confirm and plan.total_actions > 0:
        plan, skipped_categories, skipped_files = interactive_plan_confirm(plan, rules)

    plan_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]

    if output:
        planner.export_plan(plan, output)

    if output_json:
        export_plan_json(plan, output_json, plan_id, skipped_categories, skipped_files, config_path)

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
    config_path: Optional[Path],
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)
    result = None
    used_plan_id = None

    if plan_id:
        plan_data = None
        if plan_id == "last":
            plan_data = load_confirmed_plan()
            if plan_data:
                used_plan_id = plan_data.get("plan_id")
        else:
            plan_data = load_confirmed_plan(plan_id)
            used_plan_id = plan_id

        if plan_data:
            from .models import Plan, MoveAction
            plan = Plan()

            plan_config_path = plan_data.get("config_file")
            if plan_config_path and not config_path:
                click.echo(f"[FILE] 加载计划关联的配置文件: {plan_config_path}")
                rules = rule_manager.load_config(Path(plan_config_path))
                rule_manager.print_conflicts(rules)

            for a in plan_data["actions"]:
                action = MoveAction(
                    source=Path(a["source"]),
                    destination=Path(a["destination"]),
                    file_size=a["file_size"],
                )
                plan.actions.append(action)

            for cat, actions_data in plan_data.get("categories", {}).items():
                if cat not in plan.categories:
                    plan.categories[cat] = []
                for a in actions_data:
                    action = MoveAction(
                        source=Path(a["source"]),
                        destination=Path(a["destination"]),
                        file_size=a["file_size"],
                    )
                    plan.categories[cat].append(action)

            if plan.actions:
                target = plan.actions[0].destination.parent.parent

            click.echo(f"\n[PLAN] 使用计划 {used_plan_id}，共 {plan.total_actions} 个文件")
            if plan_data.get("skipped_categories"):
                click.echo(f"   已跳过分类: {', '.join(plan_data['skipped_categories'])}")
            if plan_data.get("skipped_files"):
                click.echo(f"   已跳过文件: {len(plan_data['skipped_files'])} 个")
        else:
            if plan_id == "last":
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

    if not simulate:
        if report or report_json:
            if result is None:
                source_dirs = set()
                for a in plan.actions:
                    try:
                        source_dirs.add(a.source.parents[2])
                    except (IndexError, Exception):
                        pass
                if source_dirs:
                    scan_dir = list(source_dirs)[0]
                    scanner = Scanner(root_dir=scan_dir, rules=rules)
                    result = scanner.scan()

            if report:
                Reporter.generate_organize_report(plan, log, report)
                if result:
                    Reporter.generate_savings_report(result, log, report.with_name(report.stem + "_savings" + report.suffix))

            if report_json:
                Reporter.generate_organize_report_json(plan, log, report_json, result, used_plan_id)


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
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="加载并显示用户自定义规则")
def config_command(
    show_categories: bool,
    show_excludes: bool,
    show_temp_patterns: bool,
    show_conflicts: bool,
    config_path: Optional[Path],
):
    rule_manager = RuleManager()
    rules = rule_manager.load_config(config_path)

    if config_path:
        click.echo(f"\n[FILE] 加载配置文件: {config_path}")
        rule_manager.print_conflicts(rules)

    if show_categories:
        click.echo("\n📂 分类规则")
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
        click.echo("\n🚫 排除目录")
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
            }
            for a in plan.actions
        ],
        "categories": {
            cat: [
                {
                    "source": str(a.source),
                    "destination": str(a.destination),
                    "file_size": a.file_size,
                }
                for a in actions
            ]
            for cat, actions in plan.categories.items()
        },
    }

    if scan_result:
        data["scan_summary"] = {
            "total_count": scan_result.total_count,
            "total_size": scan_result.total_size,
            "duplicate_groups": len(scan_result.duplicates),
            "duplicate_size": scan_result.duplicates_size,
            "temp_files_count": len(scan_result.temp_files),
            "temp_size": scan_result.temp_size,
            "empty_dirs_count": len(scan_result.empty_dirs),
        }

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
        "skipped": {
            "categories": list(skipped_categories),
            "files": list(skipped_files),
        },
        "categories": {
            cat: {
                "count": len(actions),
                "size": sum(a.file_size for a in actions),
                "size_human": format_size(sum(a.file_size for a in actions)),
                "actions": [
                    {
                        "source": str(a.source),
                        "destination": str(a.destination),
                        "file_size": a.file_size,
                        "file_size_human": format_size(a.file_size),
                    }
                    for a in actions
                ],
            }
            for cat, actions in plan.categories.items()
        },
    }

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
