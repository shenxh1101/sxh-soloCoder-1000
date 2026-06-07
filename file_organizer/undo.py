import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Callable

from .models import MoveLog, MoveAction, format_size
from .mover import FileMover


class UndoManager:
    def __init__(
        self,
        log_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, MoveAction], None]] = None,
    ):
        self.log_dir = Path(log_dir) if log_dir else Path.home() / ".file_organizer" / "logs"
        self.progress_callback = progress_callback

    def undo(self, log_id: Optional[str] = None, simulate: bool = False) -> Optional[MoveLog]:
        if log_id:
            log = FileMover.load_log(log_id, self.log_dir)
        else:
            logs = FileMover.list_logs(self.log_dir, limit=1)
            log = logs[0] if logs else None

        if not log:
            print(f"未找到可回滚的日志记录")
            return None

        actions_to_undo = [a for a in log.actions if a.status == "success"]

        if not actions_to_undo:
            print(f"日志 {log.log_id} 中没有可回滚的成功操作")
            return log

        print(f"\n准备回滚操作:")
        print(f"日志ID: {log.log_id}")
        print(f"执行时间: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"待回滚文件数: {len(actions_to_undo)}")

        total = len(actions_to_undo)
        completed = 0
        success_count = 0
        failed_count = 0

        for action in reversed(actions_to_undo):
            try:
                if not simulate:
                    self._undo_move(action)
                action.status = "undo_success"
                success_count += 1
            except Exception as e:
                action.status = "undo_failed"
                action.error = str(e)
                failed_count += 1

            completed += 1
            if self.progress_callback:
                self.progress_callback(completed, total, action)

        self._print_undo_summary(log, simulate, success_count, failed_count)

        return log

    def _undo_move(self, action: MoveAction) -> None:
        source = action.destination
        destination = action.source

        if not source.exists():
            raise FileNotFoundError(f"文件已不存在，无法回滚: {source}")

        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            destination = self._resolve_conflict(destination)

        shutil.move(str(source), str(destination))
        action.destination = destination

    def _resolve_conflict(self, path: Path) -> Path:
        original = path
        counter = 1
        while path.exists():
            stem = original.stem
            suffix = original.suffix
            path = original.with_name(f"{stem}_restored_{counter}{suffix}")
            counter += 1
        return path

    def _print_undo_summary(
        self,
        log: MoveLog,
        simulate: bool,
        success_count: int,
        failed_count: int,
    ) -> None:
        actions_to_undo = [a for a in log.actions if "undo" in a.status]
        total_size = sum(a.file_size for a in actions_to_undo if a.status == "undo_success")
        mode = "模拟回滚" if simulate else "实际回滚"

        print(f"\n{'='*70}")
        print(f"回滚结果 - {mode}")
        print(f"{'='*70}")
        print(f"日志ID: {log.log_id}")
        print(f"-" * 70)
        print(f"成功回滚: {success_count} 个")
        print(f"回滚失败: {failed_count} 个")
        print(f"回滚总大小: {format_size(total_size)}")
        print(f"{'='*70}\n")

    def list_history(self, limit: int = 10) -> List[MoveLog]:
        logs = FileMover.list_logs(self.log_dir, limit)

        print(f"\n{'='*70}")
        print(f"操作历史 (最近 {len(logs)} 条)")
        print(f"{'='*70}")

        source_text = {"direct": "直接执行", "plan": "计划执行"}

        for i, log in enumerate(logs, 1):
            success = sum(1 for a in log.actions if a.status == "success")
            failed = sum(1 for a in log.actions if a.status == "failed")
            size = sum(a.file_size for a in log.actions if a.status == "success")
            src = source_text.get(log.source, log.source)

            print(f"\n{i}. 日志ID: {log.log_id}")
            print(f"   时间: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   来源: {src}")
            if log.plan_id:
                print(f"   关联计划: {log.plan_id}")
            print(f"   成功: {success} 个, 失败: {failed} 个")
            print(f"   大小: {format_size(size)}")

        print(f"\n{'='*70}\n")

        return logs

    def show_log_details(self, log_id: str) -> Optional[MoveLog]:
        log = FileMover.load_log(log_id, self.log_dir)

        if not log:
            print(f"未找到日志: {log_id}")
            return None

        print(f"\n{'='*70}")
        print(f"日志详情")
        print(f"{'='*70}")
        print(f"日志ID: {log.log_id}")
        print(f"执行时间: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"操作总数: {len(log.actions)}")
        print(f"{'-'*70}")

        for i, action in enumerate(log.actions, 1):
            status_icon = {
                "success": "[OK]",
                "failed": "[X]",
                "simulated": "[SIM]",
                "undo_success": "↶",
                "undo_failed": "↷",
            }.get(action.status, "?")

            print(f"\n{i}. [{status_icon}] {action.status}")
            print(f"   源: {action.source}")
            print(f"   目标: {action.destination}")
            print(f"   大小: {format_size(action.file_size)}")
            if action.error:
                print(f"   错误: {action.error}")

        print(f"\n{'='*70}\n")

        return log
