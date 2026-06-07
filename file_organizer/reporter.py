from pathlib import Path
from datetime import datetime
from typing import Optional
from collections import defaultdict

from .models import ScanResult, Plan, MoveLog, format_size
from .config import DEFAULT_CATEGORIES


class Reporter:
    @staticmethod
    def generate_scan_report(scan_result: ScanResult, output_path: Optional[Path] = None) -> str:
        report = []
        report.append("# 文件扫描报告")
        report.append("")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("## 概览")
        report.append("")
        report.append(f"- 文件总数: {scan_result.total_count} 个")
        report.append(f"- 总大小: {format_size(scan_result.total_size)}")
        report.append(f"- 空文件夹: {len(scan_result.empty_dirs)} 个")
        report.append(f"- 重复文件组: {len(scan_result.duplicates)} 组")
        report.append(f"- 临时文件: {len(scan_result.temp_files)} 个")
        report.append(f"- 可回收空间: {format_size(scan_result.duplicates_size + scan_result.temp_size)}")
        report.append("")

        report.append("## 按类型分布")
        report.append("")
        report.append("| 类型 | 文件数 | 总大小 |")
        report.append("|------|--------|--------|")

        type_stats: dict = defaultdict(int)
        type_count: dict = defaultdict(int)
        for f in scan_result.files:
            type_stats[f.file_type] += f.size
            type_count[f.file_type] += 1

        for ftype in sorted(type_stats.keys(), key=lambda t: type_stats[t], reverse=True):
            type_name = DEFAULT_CATEGORIES.get(ftype, {}).get("name", ftype)
            report.append(f"| {type_name} | {type_count[ftype]} | {format_size(type_stats[ftype])} |")
        report.append("")

        if scan_result.duplicates:
            report.append("## 重复文件")
            report.append("")
            report.append(f"共发现 {len(scan_result.duplicates)} 组重复文件，"
                         f"浪费空间 {format_size(scan_result.duplicates_size)}")
            report.append("")
            report.append("| 序号 | 文件名 | 副本数 | 浪费空间 |")
            report.append("|------|--------|--------|----------|")
            for i, dup in enumerate(scan_result.duplicates[:50], 1):
                report.append(f"| {i} | {dup.files[0].name} | {len(dup.files)} | {format_size(dup.wasted_size)} |")
            if len(scan_result.duplicates) > 50:
                report.append(f"| ... | 还有 {len(scan_result.duplicates) - 50} 组 | | |")
            report.append("")

        if scan_result.temp_files:
            report.append("## 临时文件")
            report.append("")
            report.append(f"共发现 {len(scan_result.temp_files)} 个临时文件，"
                         f"占用空间 {format_size(scan_result.temp_size)}")
            report.append("")
            report.append("| 文件名 | 大小 |")
            report.append("|--------|------|")
            for f in scan_result.temp_files[:50]:
                report.append(f"| {f.name} | {format_size(f.size)} |")
            if len(scan_result.temp_files) > 50:
                report.append(f"| ... 还有 {len(scan_result.temp_files) - 50} 个 | |")
            report.append("")

        if scan_result.empty_dirs:
            report.append("## 空文件夹")
            report.append("")
            report.append(f"共发现 {len(scan_result.empty_dirs)} 个空文件夹")
            report.append("")
            for d in scan_result.empty_dirs[:50]:
                report.append(f"- {d}")
            if len(scan_result.empty_dirs) > 50:
                report.append(f"- ... 还有 {len(scan_result.empty_dirs) - 50} 个")
            report.append("")

        report_content = "\n".join(report)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            print(f"扫描报告已导出到: {output_path}")

        return report_content

    @staticmethod
    def generate_organize_report(
        plan: Plan,
        move_log: Optional[MoveLog] = None,
        output_path: Optional[Path] = None,
        scan_result: Optional[ScanResult] = None,
        plan_id: Optional[str] = None,
        config_file: Optional[str] = None,
        plan_data: Optional[dict] = None,
    ) -> str:
        report = []
        report.append("# 文件整理报告")
        report.append("")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        if move_log:
            success_count = sum(1 for a in move_log.actions if a.status in ("success", "simulated"))
            failed_count = sum(1 for a in move_log.actions if a.status == "failed")
            skipped_count = sum(1 for a in move_log.actions if a.status == "skipped")
            moved_size = sum(a.file_size for a in move_log.actions if a.status in ("success", "simulated"))

            source_text = {"direct": "直接执行", "plan": "计划执行"}.get(move_log.source, move_log.source)

            report.append("## 执行信息")
            report.append("")
            report.append(f"- 日志ID: {move_log.log_id}")
            report.append(f"- 执行时间: {move_log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            report.append(f"- 计划来源: {source_text}")
            if move_log.plan_id or plan_id:
                report.append(f"- 关联计划: {move_log.plan_id or plan_id}")
            if config_file:
                report.append(f"- 配置文件: {config_file}")
            report.append("")

            report.append("## 执行结果")
            report.append("")
            report.append("| 状态 | 数量 | 大小 |")
            report.append("|------|------|------|")
            report.append(f"| 成功移动 | {success_count} 个 | {format_size(moved_size)} |")
            report.append(f"| 移动失败 | {failed_count} 个 | {format_size(sum(a.file_size for a in move_log.actions if a.status == 'failed'))} |")
            report.append(f"| 跳过 | {skipped_count} 个 | {format_size(sum(a.file_size for a in move_log.actions if a.status == 'skipped'))} |")
            report.append("")

        report.append("## 整理计划")
        report.append("")
        report.append(f"- 计划移动: {plan.total_actions} 个")
        report.append(f"- 计划移动大小: {format_size(plan.total_size)}")
        report.append("")

        if scan_result:
            report.append("## 可回收空间")
            report.append("")
            report.append("| 类别 | 数量 | 可节省空间 |")
            report.append("|------|------|------------|")
            report.append(f"| 重复文件 | {len(scan_result.duplicates)} 组 | {format_size(scan_result.duplicates_size)} |")
            report.append(f"| 临时文件 | {len(scan_result.temp_files)} 个 | {format_size(scan_result.temp_size)} |")
            report.append(f"| 空文件夹 | {len(scan_result.empty_dirs)} 个 | - |")
            report.append(f"| **合计** | - | **{format_size(scan_result.duplicates_size + scan_result.temp_size)}** |")
            report.append("")

        report.append("## 按分类统计")
        report.append("")
        report.append("| 分类 | 文件数 | 大小 |")
        report.append("|------|--------|------|")

        for category in sorted(plan.categories.keys(), key=lambda c: len(plan.categories[c]), reverse=True):
            actions = plan.categories[category]
            cat_size = sum(a.file_size for a in actions)
            cat_name = DEFAULT_CATEGORIES.get(category, {}).get("name", category)
            report.append(f"| {cat_name} | {len(actions)} | {format_size(cat_size)} |")
        report.append("")

        if plan_data and plan_data.get("filter_excluded"):
            filter_excluded = plan_data["filter_excluded"]
            report.append(f"## 筛选排除的文件 ({len(filter_excluded)} 个)")
            report.append("")
            report.append("| 序号 | 文件名 | 分类 | 排除原因 |")
            report.append("|------|--------|------|----------|")
            for i, item in enumerate(filter_excluded[:50], 1):
                report.append(f"| {i} | {item['filename']} | {item.get('category', '')} | {item.get('exclude_reason', '')} |")
            if len(filter_excluded) > 50:
                report.append(f"| ... | 还有 {len(filter_excluded) - 50} 个 | | |")
            report.append("")

        if move_log and any(a.status == "skipped" for a in move_log.actions):
            report.append("## 跳过的文件")
            report.append("")
            report.append("| 序号 | 源文件 | 跳过原因 |")
            report.append("|------|--------|----------|")
            skipped = [a for a in move_log.actions if a.status == "skipped"]
            for i, action in enumerate(skipped, 1):
                report.append(f"| {i} | {action.source.name} | {action.skip_reason} |")
            report.append("")

        if move_log and any(a.status == "failed" for a in move_log.actions):
            report.append("## 失败的文件")
            report.append("")
            report.append("| 序号 | 源文件 | 错误信息 |")
            report.append("|------|--------|----------|")
            failed = [a for a in move_log.actions if a.status == "failed"]
            for i, action in enumerate(failed, 1):
                report.append(f"| {i} | {action.source.name} | {action.error} |")
            report.append("")

        if move_log and any(a.skip_reason and "自动重命名" in a.skip_reason for a in move_log.actions):
            report.append("## 自动重命名的文件")
            report.append("")
            report.append("| 序号 | 原文件名 | 新文件名 |")
            report.append("|------|----------|----------|")
            renamed = [a for a in move_log.actions if a.skip_reason and "自动重命名" in a.skip_reason]
            for i, action in enumerate(renamed, 1):
                report.append(f"| {i} | {action.source.name} | {action.destination.name} |")
            report.append("")

        report.append("## 详细操作")
        report.append("")
        report.append("| 序号 | 状态 | 源文件 | 目标文件 | 大小 | 备注 |")
        report.append("|------|------|--------|----------|------|------|")

        for i, action in enumerate(plan.actions, 1):
            status = action.status if move_log else "计划中"
            status_icon = {
                "success": "[OK]",
                "failed": "[X]",
                "simulated": "[SIM]",
                "pending": "[WAIT]",
                "skipped": "[SKIP]",
            }.get(status, "?")
            note = ""
            if action.skip_reason and "自动重命名" in action.skip_reason:
                note = "自动重命名"
            elif action.status == "skipped" and action.skip_reason:
                note = action.skip_reason
            elif action.status == "failed" and action.error:
                note = action.error
            report.append(f"| {i} | {status_icon} {status} | {action.source.name} | {action.destination.name} | {format_size(action.file_size)} | {note} |")

        report_content = "\n".join(report)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            print(f"整理报告已导出到: {output_path}")

        return report_content

    @staticmethod
    def generate_savings_report(
        scan_result: ScanResult,
        move_log: Optional[MoveLog] = None,
        output_path: Optional[Path] = None,
    ) -> str:
        report = []
        report.append("# 空间节省报告")
        report.append("")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        total_space = scan_result.total_size
        duplicates_waste = scan_result.duplicates_size
        temp_space = scan_result.temp_size
        empty_dirs_count = len(scan_result.empty_dirs)
        recoverable_space = duplicates_waste + temp_space

        report.append("## 空间分析")
        report.append("")
        report.append(f"- 总占用空间: {format_size(total_space)}")
        report.append("")
        report.append("### 可回收空间明细")
        report.append("")
        report.append("| 类别 | 数量 | 可节省空间 | 占比 |")
        report.append("|------|------|------------|------|")
        report.append(f"| 重复文件 | {len(scan_result.duplicates)} 组 | {format_size(duplicates_waste)} | "
                     f"{(duplicates_waste/total_space*100):.1f}%" if total_space > 0 else "0.0% |")
        report.append(f"| 临时文件 | {len(scan_result.temp_files)} 个 | {format_size(temp_space)} | "
                     f"{(temp_space/total_space*100):.1f}%" if total_space > 0 else "0.0% |")
        report.append(f"| 空文件夹 | {empty_dirs_count} 个 | - | - |")
        report.append(f"| **合计** | - | **{format_size(recoverable_space)}** | "
                     f"**{(recoverable_space/total_space*100):.1f}%**" if total_space > 0 else "**0.0%** |")
        report.append("")

        if move_log:
            moved_size = sum(a.file_size for a in move_log.actions if a.status == "success")
            report.append("## 整理成果")
            report.append("")
            report.append(f"- 已整理文件: {sum(1 for a in move_log.actions if a.status == 'success')} 个")
            report.append(f"- 已整理大小: {format_size(moved_size)}")
            report.append("")

        if scan_result.duplicates:
            report.append("## 重复文件详情（前20）")
            report.append("")
            report.append("| 文件名 | 副本数 | 可节省 |")
            report.append("|--------|--------|--------|")
            for dup in sorted(scan_result.duplicates, key=lambda d: d.wasted_size, reverse=True)[:20]:
                report.append(f"| {dup.files[0].name} | {len(dup.files)} | {format_size(dup.wasted_size)} |")
            report.append("")

        if scan_result.temp_files:
            report.append("## 临时文件详情（前20）")
            report.append("")
            report.append("| 文件名 | 大小 | 路径 |")
            report.append("|--------|------|------|")
            for f in sorted(scan_result.temp_files, key=lambda f: f.size, reverse=True)[:20]:
                report.append(f"| {f.name} | {format_size(f.size)} | {f.path} |")
            report.append("")

        if scan_result.empty_dirs:
            report.append("## 空文件夹详情（前20）")
            report.append("")
            for d in scan_result.empty_dirs[:20]:
                report.append(f"- {d}")
            if len(scan_result.empty_dirs) > 20:
                report.append(f"- ... 还有 {len(scan_result.empty_dirs) - 20} 个")
            report.append("")

        report_content = "\n".join(report)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            print(f"节省报告已导出到: {output_path}")

        return report_content

    @staticmethod
    def generate_scan_report_json(
        scan_result: ScanResult,
        output_path: Optional[Path] = None,
    ) -> dict:
        import json

        report_data = {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "overview": {
                "total_count": scan_result.total_count,
                "total_size": scan_result.total_size,
                "total_size_human": format_size(scan_result.total_size),
                "empty_dirs_count": len(scan_result.empty_dirs),
                "duplicate_groups": len(scan_result.duplicates),
                "duplicate_size": scan_result.duplicates_size,
                "duplicate_size_human": format_size(scan_result.duplicates_size),
                "temp_files_count": len(scan_result.temp_files),
                "temp_size": scan_result.temp_size,
                "temp_size_human": format_size(scan_result.temp_size),
                "recoverable_space": scan_result.duplicates_size + scan_result.temp_size,
                "recoverable_space_human": format_size(scan_result.duplicates_size + scan_result.temp_size),
            },
            "savings_breakdown": {
                "duplicates": {
                    "count": len(scan_result.duplicates),
                    "unit": "groups",
                    "size": scan_result.duplicates_size,
                    "size_human": format_size(scan_result.duplicates_size),
                },
                "temp_files": {
                    "count": len(scan_result.temp_files),
                    "unit": "files",
                    "size": scan_result.temp_size,
                    "size_human": format_size(scan_result.temp_size),
                },
                "empty_dirs": {
                    "count": len(scan_result.empty_dirs),
                    "unit": "dirs",
                    "size": 0,
                    "size_human": "0 B",
                },
            },
            "type_distribution": [],
            "duplicates": [],
            "temp_files": [],
            "empty_dirs": [str(d) for d in scan_result.empty_dirs],
        }

        type_stats: dict = defaultdict(int)
        type_count: dict = defaultdict(int)
        for f in scan_result.files:
            type_stats[f.file_type] += f.size
            type_count[f.file_type] += 1

        for ftype in sorted(type_stats.keys(), key=lambda t: type_stats[t], reverse=True):
            type_name = DEFAULT_CATEGORIES.get(ftype, {}).get("name", ftype)
            report_data["type_distribution"].append({
                "type": ftype,
                "name": type_name,
                "count": type_count[ftype],
                "size": type_stats[ftype],
                "size_human": format_size(type_stats[ftype]),
            })

        for dup in sorted(scan_result.duplicates, key=lambda d: d.wasted_size, reverse=True)[:100]:
            report_data["duplicates"].append({
                "name": dup.files[0].name,
                "copies": len(dup.files),
                "wasted_size": dup.wasted_size,
                "wasted_size_human": format_size(dup.wasted_size),
                "files": [{"path": str(f.path), "size": f.size} for f in dup.files],
            })

        for f in sorted(scan_result.temp_files, key=lambda f: f.size, reverse=True)[:100]:
            report_data["temp_files"].append({
                "name": f.name,
                "size": f.size,
                "size_human": format_size(f.size),
                "path": str(f.path),
            })

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f"扫描报告(JSON)已导出到: {output_path}")

        return report_data

    @staticmethod
    def generate_organize_report_json(
        plan: Plan,
        move_log: MoveLog,
        output_path: Optional[Path] = None,
        scan_result: Optional[ScanResult] = None,
        plan_id: Optional[str] = None,
        config_file: Optional[str] = None,
        plan_data: Optional[dict] = None,
    ) -> dict:
        import json

        success_count = sum(1 for a in move_log.actions if a.status in ("success", "simulated"))
        failed_count = sum(1 for a in move_log.actions if a.status == "failed")
        skipped_count = sum(1 for a in move_log.actions if a.status == "skipped")
        moved_size = sum(a.file_size for a in move_log.actions if a.status in ("success", "simulated"))
        skipped_size = sum(a.file_size for a in move_log.actions if a.status == "skipped")
        failed_size = sum(a.file_size for a in move_log.actions if a.status == "failed")

        successful_actions = [a for a in move_log.actions if a.status in ("success", "simulated")]
        failed_actions = [a for a in move_log.actions if a.status == "failed"]
        skipped_actions = [a for a in move_log.actions if a.status == "skipped"]

        report_data = {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "execution": {
                "log_id": move_log.log_id,
                "source": move_log.source,
                "plan_id": move_log.plan_id or plan_id,
                "config_file": config_file,
                "timestamp": move_log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "moved_size": moved_size,
                "moved_size_human": format_size(moved_size),
                "skipped_size": skipped_size,
                "skipped_size_human": format_size(skipped_size),
                "failed_size": failed_size,
                "failed_size_human": format_size(failed_size),
            },
            "plan": {
                "total_actions": plan.total_actions,
                "total_size": plan.total_size,
                "total_size_human": format_size(plan.total_size),
            },
            "category_stats": [],
            "details": {
                "successful": [],
                "failed": [],
                "skipped": [],
            },
        }

        for category in sorted(plan.categories.keys(), key=lambda c: len(plan.categories[c]), reverse=True):
            actions = plan.categories[category]
            cat_size = sum(a.file_size for a in actions)
            cat_name = DEFAULT_CATEGORIES.get(category, {}).get("name", category)
            report_data["category_stats"].append({
                "category": category,
                "name": cat_name,
                "count": len(actions),
                "size": cat_size,
                "size_human": format_size(cat_size),
            })

        for action in successful_actions:
            report_data["details"]["successful"].append({
                "source": str(action.source),
                "destination": str(action.destination),
                "size": action.file_size,
                "size_human": format_size(action.file_size),
                "category": action.category,
                "note": action.skip_reason if action.skip_reason and "自动重命名" in action.skip_reason else None,
            })

        for action in failed_actions:
            report_data["details"]["failed"].append({
                "source": str(action.source),
                "destination": str(action.destination),
                "size": action.file_size,
                "size_human": format_size(action.file_size),
                "category": action.category,
                "error": action.error,
            })

        for action in skipped_actions:
            report_data["details"]["skipped"].append({
                "source": str(action.source),
                "destination": str(action.destination),
                "size": action.file_size,
                "size_human": format_size(action.file_size),
                "category": action.category,
                "reason": action.skip_reason,
            })

        if scan_result:
            report_data["savings"] = {
                "duplicates": {
                    "count": len(scan_result.duplicates),
                    "size": scan_result.duplicates_size,
                    "size_human": format_size(scan_result.duplicates_size),
                },
                "temp_files": {
                    "count": len(scan_result.temp_files),
                    "size": scan_result.temp_size,
                    "size_human": format_size(scan_result.temp_size),
                },
                "empty_dirs": {
                    "count": len(scan_result.empty_dirs),
                },
                "total_recoverable": scan_result.duplicates_size + scan_result.temp_size,
                "total_recoverable_human": format_size(scan_result.duplicates_size + scan_result.temp_size),
            }

        if plan_data and plan_data.get("filter_excluded"):
            report_data["filter_excluded"] = plan_data["filter_excluded"]

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f"整理报告(JSON)已导出到: {output_path}")

        return report_data

    @staticmethod
    def print_summary(scan_result: ScanResult) -> None:
        total_space = scan_result.total_size
        recoverable = scan_result.duplicates_size + scan_result.temp_size
        percent = (recoverable / total_space * 100) if total_space > 0 else 0

        print(f"\n{'='*70}")
        print(f"[STATS] 空间节省总结")
        print(f"{'='*70}")
        print(f"总文件数: {scan_result.total_count:>8} 个")
        print(f"总空间占用: {format_size(total_space):>10}")
        print(f"{'-'*70}")
        print(f"重复文件: {len(scan_result.duplicates):>8} 组  浪费 {format_size(scan_result.duplicates_size):>10}")
        print(f"临时文件: {len(scan_result.temp_files):>8} 个  占用 {format_size(scan_result.temp_size):>10}")
        print(f"空文件夹: {len(scan_result.empty_dirs):>8} 个")
        print(f"{'-'*70}")
        print(f"可回收空间: {format_size(recoverable):>10} ({percent:.1f}%)")
        print(f"{'='*70}\n")
