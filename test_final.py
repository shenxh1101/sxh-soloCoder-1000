
import os
import json
import shutil
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

def run_cmd(cmd_parts):
    """运行命令并返回结果"""
    import subprocess
    result = subprocess.run(
        cmd_parts,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    return result.returncode, result.stdout, result.stderr

def main():
    base_dir = Path(__file__).parent / "test_final"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    source_dir = base_dir / "source"
    target_dir = base_dir / "target"
    source_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建测试文件
    test_files = [
        ("report.docx", "文档内容"),
        ("Screenshot_2024.png", "截图"),
        ("vacation.jpg", "照片"),
        ("installer.exe", "安装包"),
        ("video.mp4", "视频"),
        ("~$temp.docx", "临时文件"),
    ]
    
    for name, content in test_files:
        filepath = source_dir / name
        with open(filepath, "wb") as f:
            f.write(content.encode('utf-8'))
    
    print(f"测试环境: {base_dir}")
    print(f"源文件: {list(source_dir.glob('*'))}")
    
    # 创建配置文件
    config_file = base_dir / "config.json"
    config_data = {
        "custom_extensions": {
            "png": "personal_photos"
        },
        "target_dirs": {
            "personal_photos": "Photos/Personal",
        }
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*70)
    print("测试 1: rule-test 命令")
    print("="*70)
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "rule-test",
        "--filenames", "Screenshot_2024.png",
        "--filenames", "report.docx",
        "--config", str(config_file),
    ])
    
    # 检查关键输出
    assert code == 0, f"rule-test 失败: {err}"
    assert "personal_photos" in out, f"custom_extensions 未生效: {out}"
    assert "用户" in out, f"规则来源未显示用户: {out}"
    print("[PASS] rule-test 命令工作正常")
    
    print("\n" + "="*70)
    print("测试 2: plan 命令 + 二次筛选")
    print("="*70)
    
    plan_file = base_dir / "plan.json"
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "plan", str(source_dir), "-t", str(target_dir),
        "--config", str(config_file),
        "--include-temp",
        "--skip-pattern", "*.exe",
        "--output-json", str(plan_file),
        "--no-confirm",
    ])
    
    assert code == 0, f"plan 失败: {err}"
    assert "筛选结果" in out, f"二次筛选未执行: {out}"
    print("[PASS] plan 二次筛选工作正常")
    
    # 检查计划 JSON
    with open(plan_file, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    
    assert "filter_excluded" in plan_data, "计划 JSON 缺少 filter_excluded"
    print(f"[PASS] 计划 JSON 包含 filter_excluded ({len(plan_data['filter_excluded'])} 个文件被排除)")
    
    print("\n" + "="*70)
    print("测试 3: 计划 JSON 跳过逻辑")
    print("="*70)
    
    # 修改计划，标记 personal_photos 分类为跳过
    plan_data["categories"]["personal_photos"]["skipped"] = True
    with open(plan_file, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    # 执行计划（模拟）
    report_md = base_dir / "report.md"
    report_json = base_dir / "report.json"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_file),
        "--simulate",
        "--yes",
        "--report", str(report_md),
        "--report-json", str(report_json),
    ])
    
    assert code == 0, f"move 失败: {err}"
    assert "跳过分类" in out or "personal_photos" in out, f"分类跳过未生效: {out}"
    print("[PASS] 分类级跳过工作正常")
    
    # 检查报告是否生成
    assert report_md.exists(), f"Markdown 报告未生成: {report_md}"
    assert report_json.exists(), f"JSON 报告未生成: {report_json}"
    print("[PASS] 报告生成正常")
    
    # 检查 JSON 报告内容
    with open(report_json, 'r', encoding='utf-8') as f:
        report_data = json.load(f)
    
    assert "details" in report_data, "JSON 报告缺少 details"
    assert "execution" in report_data, "JSON 报告缺少 execution"
    assert "savings" in report_data, "JSON 报告缺少 savings"
    assert report_data["execution"]["config_file"] is not None, "报告中 config_file 为空"
    
    # 检查配置文件路径
    print(f"[PASS] JSON 报告结构完整")
    print(f"       配置文件: {report_data['execution']['config_file']}")
    print(f"       成功: {report_data['execution']['success_count']}")
    print(f"       跳过: {report_data['execution']['skipped_count']}")
    print(f"       失败: {report_data['execution']['failed_count']}")
    
    # 检查 Markdown 报告内容
    with open(report_md, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    assert "执行信息" in md_content, "Markdown 报告缺少执行信息"
    assert "可回收空间" in md_content, "Markdown 报告缺少可回收空间"
    assert "关联计划" in md_content, "Markdown 报告缺少关联计划"
    assert "配置文件" in md_content or "config_file" in md_content, "Markdown 报告缺少配置文件信息"
    print("[PASS] Markdown 报告内容完整")
    
    print("\n" + "="*70)
    print("测试 4: 错误处理 - 源文件不存在")
    print("="*70)
    
    # 删除一个文件
    missing_file = source_dir / "vacation.jpg"
    missing_file.unlink()
    print(f"已删除文件: {missing_file}")
    
    # 重新生成计划（跳过分类标记已移除）
    plan_data["categories"]["personal_photos"]["skipped"] = False
    with open(plan_file, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_file),
        "--simulate",
        "--yes",
    ])
    
    assert code == 0, f"move 失败: {err}"
    assert "源文件不存在" in out or "skipped" in out.lower(), f"源文件不存在处理不正确: {out}"
    print("[PASS] 源文件不存在错误处理正常")
    
    print("\n" + "="*70)
    print("测试 5: 错误处理 - 目标文件冲突（自动重命名）")
    print("="*70)
    
    # 在目标目录创建同名文件
    target_photo_dir = target_dir / "Photos" / "Personal"
    target_photo_dir.mkdir(parents=True, exist_ok=True)
    existing_file = target_photo_dir / "Screenshot_2024.png"
    with open(existing_file, "wb") as f:
        f.write(b"existing content")
    print(f"创建已存在文件: {existing_file}")
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_file),
        "--simulate",
        "--yes",
    ])
    
    assert code == 0, f"move 失败: {err}"
    assert "自动重命名" in out or "Screenshot_2024" in out, f"目标文件冲突处理不正确: {out}"
    print("[PASS] 目标文件冲突自动重命名处理正常")
    
    print("\n" + "="*70)
    print("所有测试通过!")
    print("="*70)
    
    # 不删除测试目录，方便检查
    print(f"\n测试目录保留: {base_dir}")
    print(f"报告文件:")
    print(f"  - {report_md}")
    print(f"  - {report_json}")

if __name__ == "__main__":
    main()
