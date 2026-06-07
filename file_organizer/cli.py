import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import click

from .scanner import Scanner
from .planner import PlanGenerator
from .mover import FileMover
from .undo import UndoManager
from .reporter import Reporter
from .models import format_size
from .config import DEFAULT_EXCLUDE_DIRS, DEFAULT_CATEGORIES


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


def parse_date(date_str: str) -> datetime:
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
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
        status = "✓" if action.status == "success" else "○"
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
@click.option("--quiet", "-q", is_flag=True, help="静默模式，只输出结果摘要")
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
    quiet: bool,
):
    directory = directory.resolve()

    exclude_dirs = list(DEFAULT_EXCLUDE_DIRS) + list(exclude)
    min_size = parse_size(min_size_str)
    max_size = parse_size(max_size_str) if max_size_str != "-1" else -1

    dt_from = parse_date(date_from) if date_from else None
    dt_to = parse_date(date_to) if date_to else None

    click.echo(f"\n🔍 开始扫描目录: {directory}")
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

    scan_cache = Path.home() / ".file_organizer" / "last_scan.json"
    scan_cache.parent.mkdir(parents=True, exist_ok=True)
    scan_data = {
        "directory": str(directory),
        "timestamp": datetime.now().isoformat(),
        "file_count": result.total_count,
        "total_size": result.total_size,
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
@click.option("--detail", "-d", "show_detail", is_flag=True, help="显示详细计划")
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
    show_detail: bool,
):
    directory = directory.resolve()
    target = target.resolve()

    click.echo(f"\n📋 生成整理计划")
    click.echo(f"源目录: {directory}")
    click.echo(f"目标目录: {target}")
    click.echo(f"整理方式: {organize_by}")
    click.echo("-" * 60)

    exclude_dirs = list(DEFAULT_EXCLUDE_DIRS) + list(exclude)

    with click.progressbar(length=1, label="扫描文件") as bar:
        scanner = Scanner(
            root_dir=directory,
            exclude_dirs=exclude_dirs,
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
    )

    plan = planner.generate()
    planner.print_plan(plan, show_details=show_detail)

    if output:
        planner.export_plan(plan, output)

    plan_cache = Path.home() / ".file_organizer" / "last_plan.json"
    plan_cache.parent.mkdir(parents=True, exist_ok=True)

    actions_data = [
        {
            "source": str(a.source),
            "destination": str(a.destination),
            "file_size": a.file_size,
        }
        for a in plan.actions
    ]

    with open(plan_cache, "w", encoding="utf-8") as f:
        json.dump(actions_data, f, ensure_ascii=False, indent=2)


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
@click.option("--report", "-r", type=click.Path(path_type=Path), help="导出整理报告")
@click.option("--from-plan", is_flag=True, help="使用上次生成的计划")
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
    from_plan: bool,
):
    if from_plan:
        plan_cache = Path.home() / ".file_organizer" / "last_plan.json"
        if not plan_cache.exists():
            click.echo("❌ 未找到上次的计划，请先运行 plan 命令")
            sys.exit(1)

        with open(plan_cache, "r", encoding="utf-8") as f:
            actions_data = json.load(f)

        from .models import Plan, MoveAction
        plan = Plan()
        for a in actions_data:
            action = MoveAction(
                source=Path(a["source"]),
                destination=Path(a["destination"]),
                file_size=a["file_size"],
            )
            plan.actions.append(action)

        if plan.actions:
            target = plan.actions[0].destination.parent.parent

        click.echo(f"\n📦 使用上次的计划，共 {plan.total_actions} 个文件")
    else:
        if not directory or not target:
            click.echo("❌ 请指定源目录和目标目录，或使用 --from-plan")
            sys.exit(1)

        directory = directory.resolve()
        target = target.resolve()

        click.echo(f"\n{'⚠️  模拟执行' if simulate else '🚀 执行整理'}")
        click.echo(f"源目录: {directory}")
        click.echo(f"目标目录: {target}")
        click.echo("-" * 60)

        exclude_dirs = list(DEFAULT_EXCLUDE_DIRS) + list(exclude)

        with click.progressbar(length=1, label="扫描文件") as bar:
            scanner = Scanner(
                root_dir=directory,
                exclude_dirs=exclude_dirs,
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

    log = mover.execute(simulate=simulate)
    FileMover.print_execution_summary(log, simulate=simulate)

    if report and not simulate:
        Reporter.generate_organize_report(plan, log, report)
        Reporter.generate_savings_report(result, log, report.with_name(report.stem + "_savings" + report.suffix))


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
            click.echo("❌ 没有可回滚的操作记录")
            return
        log_id = logs[0].log_id
        click.echo(f"将回滚最近一次操作: {log_id}")

    log = FileMover.load_log(log_id)
    if not log:
        click.echo(f"❌ 未找到日志: {log_id}")
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
def config_command(
    show_categories: bool,
    show_excludes: bool,
    show_temp_patterns: bool,
):
    if show_categories:
        click.echo("\n📂 分类规则")
        click.echo("=" * 60)
        for key, config in DEFAULT_CATEGORIES.items():
            click.echo(f"\n{config.get('name', key)} ({key})")
            click.echo(f"  目标目录: {config.get('target_dir', 'Other')}")
            if "extensions" in config:
                click.echo(f"  扩展名: {', '.join(config['extensions'])}")
            if "patterns" in config:
                click.echo(f"  命名模式:")
                for p in config["patterns"]:
                    click.echo(f"    - {p}")
        click.echo()

    if show_excludes:
        click.echo("\n🚫 默认排除目录")
        click.echo("=" * 60)
        for d in DEFAULT_EXCLUDE_DIRS:
            click.echo(f"  - {d}")
        click.echo()

    if show_temp_patterns:
        from .config import TEMP_PATTERNS
        click.echo("\n🗑️  临时文件匹配规则")
        click.echo("=" * 60)
        for p in TEMP_PATTERNS:
            click.echo(f"  - {p.pattern}")
        click.echo()

    if not any([show_categories, show_excludes, show_temp_patterns]):
        click.echo("\n⚙️  文件整理工具配置")
        click.echo("=" * 60)
        click.echo(f"分类数量: {len(DEFAULT_CATEGORIES)}")
        click.echo(f"排除目录: {len(DEFAULT_EXCLUDE_DIRS)} 个")
        click.echo(f"临时文件规则: {len(DEFAULT_EXCLUDE_DIRS)} 个")
        click.echo()
        click.echo("使用以下选项查看详细信息:")
        click.echo("  --show-categories    显示分类规则")
        click.echo("  --show-excludes      显示排除目录")
        click.echo("  --show-temp-patterns 显示临时文件规则")
        click.echo()


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n\n操作已取消")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n❌ 错误: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
