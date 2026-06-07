
import os
import json
import shutil
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

def create_test_environment():
    """创建测试环境"""
    # 使用当前工作目录，避免被 AppData 排除规则过滤
    base_dir = Path(__file__).parent / "test_data_phase4"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    tmpdir = base_dir
    source_dir = tmpdir / "source"
    target_dir = tmpdir / "target"
    
    source_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 创建测试文件
    test_files = [
        # 文档
        ("report.docx", "这是一份文档"),
        ("data.xlsx", "Excel数据"),
        ("Screenshot_2024.png", "截图文件"),
        ("vacation.jpg", "个人照片"),
        ("installer.exe", "安装程序"),
        ("video.mp4", "视频文件"),
        ("~$temp.docx", "临时文件"),
        ("Screenshot_2024(1).png", "截图文件副本"),
    ]
    
    for name, content in test_files:
        filepath = source_dir / name
        filepath.write_text(content, encoding='utf-8')
        # 设置不同的大小
        with open(filepath, "wb") as f:
            f.write(content.encode('utf-8'))
    
    print(f"测试环境已创建: {tmpdir}")
    print(f"源目录: {source_dir}")
    print(f"目标目录: {target_dir}")
    return source_dir, target_dir, tmpdir

def run_test():
    source_dir, target_dir, tmpdir = create_test_environment()
    
    try:
        print("\n" + "="*80)
        print("测试 1: rule-test 命令")
        print("="*80)
        
        import subprocess
        
        # 创建配置文件
        config_file = Path(tmpdir) / "config.json"
        config_data = {
            "custom_extensions": {
                "png": "personal_photos"
            },
            "target_dirs": {
                "personal_photos": "我的图片/个人照片",
            },
            "exclude_dirs": ["node_modules"]
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        print(f"\n配置文件: {config_file}")
        print("内容:")
        print(json.dumps(config_data, ensure_ascii=False, indent=2))
        
        # 测试 rule-test
        print("\n--- 测试 rule-test ---\n")
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "rule-test",
            "--filenames", "Screenshot_2024.png",
            "--filenames", "report.docx",
            "--filenames", "installer.exe",
            "--filenames", "data.xlsx",
            "--config", str(config_file),
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])
        
        print("\n--- 测试 rule-test 带目录扫描 ---\n")
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "rule-test",
            str(source_dir),
            "--config", str(config_file),
            "--output-json", str(Path(tmpdir) / "rule_test_result.json"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        print("\n" + "="*80)
        print("测试 2: plan 二次筛选")
        print("="*80)
        
        print("\n--- 测试 plan --only-category ---\n")
        plan_file = Path(tmpdir) / "plan_full.json"
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "plan", str(source_dir), "-t", str(target_dir),
            "--config", str(config_file),
            "--include-temp",
            "--output-json", str(plan_file),
            "--no-confirm",
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])
        
        print("\n--- 测试 plan 带筛选 ---\n")
        plan_filtered = Path(tmpdir) / "plan_filtered.json"
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "plan", str(source_dir), "-t", str(target_dir),
            "--config", str(config_file),
            "--include-temp",
            "--only-category", "personal_photos",
            "--output-json", str(plan_filtered),
            "--no-confirm",
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])
        
        print("\n--- 查看筛选后的计划 JSON ---\n")
        with open(plan_filtered, 'r', encoding='utf-8') as f:
            plan_data_filtered = json.load(f)
        print("JSON 结构:", json.dumps(plan_data_filtered, ensure_ascii=False, indent=2))

        print("\n" + "="*80)
        print("测试 3: 计划 JSON 跳过逻辑")
        print("="*80)
        
        print("\n--- 修改计划，标记分类跳过 ---\n")
        # 读取完整计划并修改，将 personal_photos 分类标记为跳过
        with open(plan_file, 'r', encoding='utf-8') as f:
            plan_data_full = json.load(f)
        plan_data_full["categories"]["personal_photos"]["skipped"] = True
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(plan_data_full, f, ensure_ascii=False, indent=2)
        
        # 设置 plan_data 变量供后续使用
        plan_data = plan_data_full
        
        # 测试 move --plan-file --simulate
        report_md = Path(tmpdir) / "report.md"
        report_json = Path(tmpdir) / "report.json"
        
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "move",
            "--plan-file", str(plan_file),
            "--simulate",
            "--yes",
            "--report", str(report_md),
            "--report-json", str(report_json),
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])
        
        print("\n--- 查看 JSON 报告 ---\n")
        with open(report_json, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        print("JSON 报告结构:")
        print(json.dumps(report_data, ensure_ascii=False, indent=2))
        
        print("\n--- 查看 Markdown 报告 ---\n")
        with open(report_md, 'r', encoding='utf-8') as f:
            print(f.read())

        print("\n" + "="*80)
        print("测试 4: 错误处理 - 源文件不存在")
        print("="*80)
        
        print("\n--- 手动删除一个文件，测试跳过 ---\n")
        # 删除一个文件
        missing_file = source_dir / "Screenshot_2024.png"
        print(f"删除文件: {missing_file}")
        missing_file.unlink()
        
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "move",
            "--plan-file", str(plan_file),
            "--simulate",
            "--yes",
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])

        print("\n" + "="*80)
        print("测试 5: 错误处理 - 目标文件已存在")
        print("="*80)
        
        print("\n--- 创建目标文件已存在的情况 ---\n")
        # 手动在目标目录创建一个同名文件，测试自动重命名
        target_photo_dir = target_dir / "我的图片" / "个人照片"
        target_photo_dir.mkdir(parents=True, exist_ok=True)
        existing_file = target_photo_dir / "Screenshot_2024(1).png"
        existing_file.write_text("已存在的文件", encoding='utf-8')
        print(f"创建已存在文件: {existing_file}")
        
        # 重新生成一个没有跳过标记的计划
        plan_no_skip = Path(tmpdir) / "plan_no_skip.json"
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "plan", str(source_dir), "-t", str(target_dir),
            "--config", str(config_file),
            "--include-temp",
            "--output-json", str(plan_no_skip),
            "--no-confirm",
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        
        cmd = [
            sys.executable, "-m", "file_organizer.cli",
            "move",
            "--plan-file", str(plan_no_skip),
            "--simulate",
            "--yes",
            "--report", str(Path(tmpdir) / "report_conflict.md"),
            "--report-json", str(Path(tmpdir) / "report_conflict.json"),
        ]
        print(f"命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.stdout:
            cleaned_output = result.stdout.replace('█', '').replace('░', '').replace('▓', '')
            print("STDOUT:", cleaned_output[:3000])
        if result.stderr:
            cleaned_stderr = result.stderr.replace('█', '').replace('░', '').replace('▓', '')
            print("STDERR:", cleaned_stderr[:1000])

        print("\n" + "="*80)
        print("测试完成")
        print(f"测试目录: {tmpdir}")
        print("="*80)
        
    finally:
        # 清理测试环境
        print(f"\n清理测试环境...")
        # shutil.rmtree(tmpdir)
        print(f"测试目录保留以便检查: {tmpdir}")
        print(f"如需清理，请手动删除: rm -rf {tmpdir}")

if __name__ == "__main__":
    run_test()
