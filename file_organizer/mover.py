import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Callable
from collections import defaultdict

try:
    from send2trash import send2trash
    USE_TRASH = True
except ImportError:
    USE_TRASH = False

from .models import Plan, MoveAction, MoveLog, format_size


class FileMover:
    def __init__(
        self,
        plan: Plan,
        log_dir: Optional[Path] = None,
        use_trash: bool = True,
        progress_callback: Optional[Callable[[int, int, MoveAction], None]] = None,
    ):
        self.plan = plan
        self.log_dir = Path(log_dir) if log_dir else Path.home() / ".file_organizer" / "logs"
        self.use_trash = use_trash and USE_TRASH
        self.progress_callback = progress_callback
        self.current_log: Optional[MoveLog] = None

    def execute(self, simulate: bool = False, source: str = "direct", plan_id: Optional[str] = None) -> MoveLog:
        log_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.current_log = MoveLog(
            log_id=log_id,
            timestamp=datetime.now(),
            actions=[],
            source=source,
            plan_id=plan_id,
        )

        total = len(self.plan.actions)
        completed = 0

        for action in self.plan.actions:
            if action.status == "skipped":
                self.current_log.actions.append(action)
                completed += 1
                if self.progress_callback:
                    self.progress_callback(completed, total, action)
                continue

            action.status = "pending"
            action.error = None
            old_skip_reason = action.skip_reason
            action.skip_reason = None

            if not simulate:
                try:
                    self._move_file(action)
                    action.status = "success"
                except FileNotFoundError as e:
                    action.status = "skipped"
                    action.skip_reason = f"源文件不存在: {str(e)}"
                except FileExistsError as e:
                    action.status = "failed"
                    action.error = f"目标文件已存在且无法自动重命名: {str(e)}"
                except Exception as e:
                    action.status = "failed"
                    action.error = str(e)
            else:
                try:
                    self._simulate_move(action)
                    action.status = "simulated"
                except FileNotFoundError as e:
                    action.status = "skipped"
                    action.skip_reason = f"源文件不存在: {str(e)}"
                except Exception as e:
                    action.status = "failed"
                    action.error = str(e)

            if old_skip_reason and "自动重命名" in old_skip_reason and action.status in ("success", "simulated"):
                action.skip_reason = old_skip_reason

            self.current_log.actions.append(action)
            completed += 1

            if self.progress_callback:
                self.progress_callback(completed, total, action)

        if not simulate:
            self._save_log()

        return self.current_log

    def _simulate_move(self, action: MoveAction) -> None:
        source = action.source
        destination = action.destination

        if not source.exists():
            raise FileNotFoundError(f"源文件不存在: {source}")

        if destination.exists():
            new_dest = self._resolve_conflict(destination)
            if new_dest != destination:
                action.destination = new_dest
                action.skip_reason = f"目标文件已存在，将自动重命名为: {new_dest.name}"

    def _move_file(self, action: MoveAction) -> None:
        source = action.source
        destination = action.destination

        if not source.exists():
            raise FileNotFoundError(f"源文件不存在: {source}")

        destination.parent.mkdir(parents=True, exist_ok=True)

        original_dest = destination
        if destination.exists():
            destination = self._resolve_conflict(destination)
            action.destination = destination
            if original_dest != destination:
                action.skip_reason = f"目标文件已存在，自动重命名为: {destination.name}"

        shutil.move(str(source), str(destination))

    def _resolve_conflict(self, path: Path) -> Path:
        original = path
        counter = 1
        while path.exists():
            stem = original.stem
            suffix = original.suffix
            path = original.with_name(f"{stem}_{counter}{suffix}")
            counter += 1
        return path

    def _save_log(self) -> None:
        if not self.current_log:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / f"{self.current_log.log_id}.json"

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self.current_log.to_dict(), f, ensure_ascii=False, indent=2)

    def delete_temp_files(self, file_paths: List[Path]) -> dict:
        result = {
            "success": [],
            "failed": [],
            "total_size": 0,
        }

        for path in file_paths:
            try:
                size = path.stat().st_size
                if self.use_trash:
                    send2trash(str(path))
                else:
                    path.unlink()
                result["success"].append(path)
                result["total_size"] += size
            except Exception as e:
                result["failed"].append((path, str(e)))

        return result

    def delete_empty_dirs(self, dir_paths: List[Path]) -> dict:
        result = {
            "success": [],
            "failed": [],
        }

        sorted_dirs = sorted(dir_paths, key=lambda d: len(str(d)), reverse=True)

        for dir_path in sorted_dirs:
            try:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    result["success"].append(dir_path)
            except Exception as e:
                result["failed"].append((dir_path, str(e)))

        return result

    def delete_duplicates(self, keep_original: bool = True) -> dict:
        from .scanner import ScanResult

        result = {
            "groups": 0,
            "deleted": [],
            "failed": [],
            "saved_size": 0,
        }

        return result

    @staticmethod
    def print_execution_summary(log: MoveLog, simulate: bool = False) -> None:
        success_count = sum(1 for a in log.actions if a.status in ("success", "simulated"))
        failed_count = sum(1 for a in log.actions if a.status == "failed")
        skipped_count = sum(1 for a in log.actions if a.status == "skipped")
        total_size = sum(a.file_size for a in log.actions if a.status in ("success", "simulated"))

        mode = "模拟执行" if simulate else "实际执行"
        source_text = {"direct": "直接执行", "plan": "计划执行"}.get(log.source, log.source)

        print(f"\n{'='*70}")
        print(f"执行结果 - {mode}")
        print(f"{'='*70}")
        print(f"日志ID: {log.log_id}")
        print(f"执行时间: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"来源: {source_text}")
        if log.plan_id:
            print(f"关联计划: {log.plan_id}")
        print(f"-" * 70)
        print(f"成功: {success_count} 个")
        print(f"失败: {failed_count} 个")
        print(f"跳过: {skipped_count} 个")
        print(f"移动总大小: {format_size(total_size)}")
        print(f"{'='*70}")

        if skipped_count > 0:
            print(f"\n跳过的文件:")
            for action in log.actions:
                if action.status == "skipped":
                    print(f"  [SKIP] {action.source.name}: {action.skip_reason}")

        if failed_count > 0:
            print(f"\n失败的文件:")
            for action in log.actions:
                if action.status == "failed":
                    print(f"  [FAIL] {action.source.name}: {action.error}")

        renamed_count = sum(1 for a in log.actions if a.skip_reason and "自动重命名" in a.skip_reason)
        if renamed_count > 0:
            print(f"\n自动重命名的文件:")
            for action in log.actions:
                if action.skip_reason and "自动重命名" in action.skip_reason:
                    status_icon = "[SIM]" if action.status == "simulated" else "[OK]"
                    print(f"  {status_icon} {action.source.name} -> {action.destination.name}")

        print()

    @staticmethod
    def list_logs(log_dir: Optional[Path] = None, limit: int = 10) -> List[MoveLog]:
        log_dir = Path(log_dir) if log_dir else Path.home() / ".file_organizer" / "logs"
        if not log_dir.exists():
            return []

        log_files = sorted(log_dir.glob("*.json"), reverse=True)[:limit]
        logs = []

        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logs.append(MoveLog.from_dict(data))
            except Exception:
                continue

        return logs

    @staticmethod
    def load_log(log_id: str, log_dir: Optional[Path] = None) -> Optional[MoveLog]:
        log_dir = Path(log_dir) if log_dir else Path.home() / ".file_organizer" / "logs"
        log_file = log_dir / f"{log_id}.json"

        if not log_file.exists():
            return None

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return MoveLog.from_dict(data)
        except Exception:
            return None
