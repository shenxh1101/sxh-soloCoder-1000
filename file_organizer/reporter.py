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
    ) -> str:
        report = []
        report.append("# 文件整理报告")
        report.append("")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        if move_log:
            success_count = sum(1 for a in move_log.actions if a.status == "success")
            failed_count = sum(1 for a in move_log.actions if a.status == "failed")
            moved_size = sum(a.file_size for a in move_log.actions if a.status == "success")

            report.append("## 执行结果")
            report.append("")
            report.append(f"- 日志ID: {move_log.log_id}")
            report.append(f"- 执行时间: {move_log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            report.append(f"- 成功移动: {success_count} 个")
            report.append(f"- 移动失败: {failed_count} 个")
            report.append(f"- 移动总大小: {format_size(moved_size)}")
            report.append("")

        report.append("## 整理计划")
        report.append("")
        report.append(f"- 计划移动: {plan.total_actions} 个")
        report.append(f"- 计划移动大小: {format_size(plan.total_size)}")
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

        report.append("## 详细操作")
        report.append("")
        report.append("| 序号 | 状态 | 源文件 | 目标文件 | 大小 |")
        report.append("|------|------|--------|----------|------|")

        for i, action in enumerate(plan.actions, 1):
            status = action.status if move_log else "计划中"
            status_icon = {
                "success": "✓",
                "failed": "✗",
                "simulated": "○",
                "pending": "⏳",
            }.get(status, "?")
            report.append(f"| {i} | {status_icon} {status} | {action.source} | {action.destination} | {format_size(action.file_size)} |")

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
        recoverable_space = duplicates_waste + temp_space

        report.append("## 空间分析")
        report.append("")
        report.append(f"- 总占用空间: {format_size(total_space)}")
        report.append(f"- 重复文件浪费: {format_size(duplicates_waste)} "
                     f"({duplicates_waste/total_space*100:.1f}%)" if total_space > 0 else "")
        report.append(f"- 临时文件占用: {format_size(temp_space)} "
                     f"({temp_space/total_space*100:.1f}%)" if total_space > 0 else "")
        report.append(f"- 可回收空间总计: {format_size(recoverable_space)} "
                     f"({recoverable_space/total_space*100:.1f}%)" if total_space > 0 else "")
        report.append("")

        if move_log:
            moved_size = sum(a.file_size for a in move_log.actions if a.status == "success")
            report.append("## 整理成果")
            report.append("")
            report.append(f"- 已整理文件: {sum(1 for a in move_log.actions if a.status == 'success')} 个")
            report.append(f"- 已整理大小: {format_size(moved_size)}")
            report.append("")

        if scan_result.duplicates:
            report.append("## 重复文件详情")
            report.append("")
            report.append("| 文件名 | 副本数 | 可节省 |")
            report.append("|--------|--------|--------|")
            for dup in sorted(scan_result.duplicates, key=lambda d: d.wasted_size, reverse=True)[:20]:
                report.append(f"| {dup.files[0].name} | {len(dup.files)} | {format_size(dup.wasted_size)} |")
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
    def print_summary(scan_result: ScanResult) -> None:
        total_space = scan_result.total_size
        recoverable = scan_result.duplicates_size + scan_result.temp_size
        percent = (recoverable / total_space * 100) if total_space > 0 else 0

        print(f"\n{'='*70}")
        print(f"📊 空间节省总结")
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
