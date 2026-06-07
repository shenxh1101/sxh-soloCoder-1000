
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

def check_report_consistency(report_md, report_json, expected):
    """检查报告一致性"""
    print("\n--- 报告一致性校验 ---")
    
    with open(report_json, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    with open(report_md, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    exec_data = json_data["execution"]
    print(f"JSON 执行统计:")
    print(f"  成功: {exec_data['success_count']}")
    print(f"  跳过: {exec_data['skipped_count']}")
    print(f"  失败: {exec_data['failed_count']}")
    
    assert exec_data["success_count"] == expected["success"], \
        f"JSON 成功数不匹配: {exec_data['success_count']} != {expected['success']}"
    assert exec_data["skipped_count"] == expected["skipped"], \
        f"JSON 跳过数不匹配: {exec_data['skipped_count']} != {expected['skipped']}"
    assert exec_data["failed_count"] == expected["failed"], \
        f"JSON 失败数不匹配: {exec_data['failed_count']} != {expected['failed']}"
    
    if expected["success"] > 0:
        assert "成功移动" in md_content, "Markdown 缺少成功移动统计"
    if expected["skipped"] > 0:
        assert "跳过" in md_content, "Markdown 缺少跳过统计"
        assert "跳过的文件" in md_content, "Markdown 缺少跳过文件列表"
    if expected["failed"] > 0:
        assert "移动失败" in md_content, "Markdown 缺少失败统计"
        assert "失败的文件" in md_content, "Markdown 缺少失败文件列表"
    
    print("[PASS] 报告一致性校验通过")
    return json_data

def main():
    base_dir = Path(__file__).parent / "test_bugfixes"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    source_dir = base_dir / "source"
    target_dir = base_dir / "target"
    source_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建测试文件
    test_files = [
        ("report.docx", "文档"),
        ("data.xlsx", "表格"),
        ("Screenshot_2024.png", "截图"),
        ("vacation.jpg", "照片"),
        ("installer.exe", "安装包"),
        ("video.mp4", "视频"),
        ("movie.avi", "视频2"),
        ("notes.txt", "文本"),
    ]
    
    for name, content in test_files:
        filepath = source_dir / name
        with open(filepath, "wb") as f:
            f.write(content.encode('utf-8'))
    
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
    
    print(f"测试环境: {base_dir}")
    print(f"源文件: {[f.name for f in source_dir.glob('*')]}")
    
    print("\n" + "="*70)
    print("测试 1: 入口加载测试")
    print("="*70)
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "--help"
    ])
    assert code == 0, f"入口加载失败: {err}"
    assert "scan" in out and "plan" in out and "move" in out and "rule-test" in out, \
        f"命令列表不完整: {out}"
    print("[PASS] 入口加载正常，所有命令可用")
    
    print("\n" + "="*70)
    print("测试 2: plan 二次筛选 - Markdown 显示筛选排除的文件")
    print("="*70)
    
    plan_file = base_dir / "plan_filtered.json"
    plan_md = base_dir / "plan_filtered.md"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "plan", str(source_dir), "-t", str(target_dir),
        "--config", str(config_file),
        "--skip-pattern", "*.exe",
        "--skip-pattern", "*.mp4",
        "--skip-regex", r"^Screenshot_.*",
        "--output-json", str(plan_file),
        "-o", str(plan_md),
        "--no-confirm",
    ])
    assert code == 0, f"plan 失败: {err}"
    assert "筛选结果" in out, f"筛选未执行: {out}"
    
    # 检查 JSON 中的 filter_excluded
    with open(plan_file, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    
    assert "filter_excluded" in plan_data, "JSON 缺少 filter_excluded"
    filter_excluded = plan_data["filter_excluded"]
    print(f"筛选排除 {len(filter_excluded)} 个文件:")
    for item in filter_excluded:
        print(f"  - {item['filename']} (分类: {item.get('category')}, 原因: {item.get('exclude_reason')})")
    
    # 检查每个被排除的文件是否有必要的字段
    for item in filter_excluded:
        assert "filename" in item, "缺少 filename 字段"
        assert "category" in item, "缺少 category 字段"
        assert "exclude_reason" in item, "缺少 exclude_reason 字段"
    
    # 检查 Markdown 中是否显示了筛选排除的文件
    with open(plan_md, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    assert "筛选排除的文件" in md_content, "Markdown 缺少筛选排除的文件部分"
    for item in filter_excluded:
        assert item["filename"] in md_content, f"Markdown 中缺少 {item['filename']}"
        assert item.get("category", "") in md_content, f"Markdown 中缺少 {item['filename']} 的分类信息"
        assert item.get("exclude_reason", "") in md_content, f"Markdown 中缺少 {item['filename']} 的排除原因"
    
    print("[PASS] 二次筛选 - Markdown 和 JSON 信息一致")
    
    print("\n" + "="*70)
    print("测试 3: 计划 JSON 跳过逻辑 - 只改总列表中的 skipped")
    print("="*70)
    
    # 先导出完整计划
    plan_full = base_dir / "plan_full.json"
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "plan", str(source_dir), "-t", str(target_dir),
        "--config", str(config_file),
        "--output-json", str(plan_full),
        "--no-confirm",
    ])
    assert code == 0, f"plan 失败: {err}"
    
    with open(plan_full, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    
    # 只修改总列表中 vacation.jpg 的 skipped 为 true，不修改分类列表中的
    for a in plan_data["actions"]:
        if "vacation.jpg" in a["source"]:
            a["skipped"] = True
            print(f"修改总列表中 vacation.jpg 的 skipped = true")
            break
    
    # 确保分类列表中的 vacation.jpg 没有修改
    for cat, cat_data in plan_data["categories"].items():
        for a in cat_data["actions"]:
            if "vacation.jpg" in a["source"]:
                assert not a.get("skipped", False), "分类列表中的 skipped 不应被修改"
    
    with open(plan_full, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    # 执行计划
    report_md = base_dir / "report_test3.md"
    report_json = base_dir / "report_test3.json"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_full),
        "--simulate",
        "--yes",
        "--report", str(report_md),
        "--report-json", str(report_json),
    ])
    assert code == 0, f"move 失败: {err}"
    
    # 检查终端输出
    print(f"终端输出:")
    print(out[-500:] if len(out) > 500 else out)
    
    assert "将跳过: 1" in out or "将跳过:  1" in out, f"跳过数量不正确: {out}"
    assert "vacation.jpg" in out or "vacation" in out, f"跳过文件未显示: {out}"
    
    # 检查报告
    json_data = check_report_consistency(report_md, report_json, {
        "success": 7,  # 8个文件 - 1个跳过
        "skipped": 1,
        "failed": 0
    })
    
    # 检查跳过的文件明细
    skipped_details = json_data["details"]["skipped"]
    assert len(skipped_details) == 1, f"跳过明细数量不正确: {len(skipped_details)}"
    assert "vacation.jpg" in skipped_details[0]["source"], "跳过的文件不是 vacation.jpg"
    assert "文件跳过" in skipped_details[0]["reason"], "跳过原因不正确"
    print(f"跳过原因: {skipped_details[0]['reason']}")
    
    print("[PASS] 只改总列表 skipped 也能正确跳过")
    
    print("\n" + "="*70)
    print("测试 4: 计划 JSON 跳过逻辑 - 分类跳过在报告中显示")
    print("="*70)
    
    # 重新加载完整计划并修改分类跳过
    with open(plan_full, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    
    # 将 documents 分类标记为跳过
    plan_data["categories"]["documents"]["skipped"] = True
    print(f"将 documents 分类标记为跳过 (包含 {len(plan_data['categories']['documents']['actions'])} 个文件)")
    
    # 移除之前的文件级跳过
    for a in plan_data["actions"]:
        if "skipped" in a:
            del a["skipped"]
    
    with open(plan_full, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    # 执行计划
    report_md4 = base_dir / "report_test4.md"
    report_json4 = base_dir / "report_test4.json"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_full),
        "--simulate",
        "--yes",
        "--report", str(report_md4),
        "--report-json", str(report_json4),
    ])
    assert code == 0, f"move 失败: {err}"
    
    # 检查终端输出
    print(f"终端输出:")
    print(out[-500:] if len(out) > 500 else out)
    
    assert "跳过分类: documents" in out, f"分类跳过未显示: {out}"
    
    # 计算文档分类的文件数
    doc_count = len(plan_data["categories"]["documents"]["actions"])
    expected_skipped = doc_count  # documents 分类中的文件数
    
    # 检查报告
    json_data4 = check_report_consistency(report_md4, report_json4, {
        "success": 8 - expected_skipped,
        "skipped": expected_skipped,
        "failed": 0
    })
    
    # 检查跳过的文件明细
    skipped_details = json_data4["details"]["skipped"]
    assert len(skipped_details) == expected_skipped, f"跳过明细数量不正确: {len(skipped_details)}"
    for item in skipped_details:
        assert "分类跳过" in item["reason"], f"跳过原因应包含'分类跳过': {item['reason']}"
        assert "documents" in item["reason"], f"跳过原因应包含'documents': {item['reason']}"
    
    print(f"[PASS] 分类跳过在报告中显示正确，共 {expected_skipped} 个文件")
    
    print("\n" + "="*70)
    print("测试 5: 源文件不存在 - 报告一致性校验")
    print("="*70)
    
    # 重新生成计划
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "plan", str(source_dir), "-t", str(target_dir),
        "--config", str(config_file),
        "--output-json", str(plan_full),
        "--no-confirm",
    ])
    
    # 删除一个文件
    missing_file = source_dir / "video.mp4"
    missing_file.unlink()
    print(f"已删除文件: {missing_file}")
    
    # 执行计划
    report_md5 = base_dir / "report_test5.md"
    report_json5 = base_dir / "report_test5.json"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_full),
        "--simulate",
        "--yes",
        "--report", str(report_md5),
        "--report-json", str(report_json5),
    ])
    assert code == 0, f"move 失败: {err}"
    
    # 检查报告一致性
    json_data5 = check_report_consistency(report_md5, report_json5, {
        "success": 7,  # 8个文件 - 1个删除
        "skipped": 1,  # 源文件不存在
        "failed": 0
    })
    
    # 检查跳过原因
    skipped_details = json_data5["details"]["skipped"]
    assert len(skipped_details) == 1
    assert "源文件不存在" in skipped_details[0]["reason"], f"跳过原因不正确: {skipped_details[0]['reason']}"
    assert "video.mp4" in skipped_details[0]["source"], "跳过的文件不是 video.mp4"
    
    # 检查 Markdown
    with open(report_md5, 'r', encoding='utf-8') as f:
        md5 = f.read()
    assert "源文件不存在" in md5, "Markdown 中缺少源文件不存在信息"
    assert "video.mp4" in md5, "Markdown 中缺少 video.mp4"
    
    print("[PASS] 源文件不存在 - 报告一致性校验通过")
    
    print("\n" + "="*70)
    print("测试 6: 目标文件冲突自动改名 - 报告一致性校验")
    print("="*70)
    
    # 重新创建被删除的文件
    with open(missing_file, "wb") as f:
        f.write(b"video content")
    
    # 重新生成计划
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "plan", str(source_dir), "-t", str(target_dir),
        "--config", str(config_file),
        "--output-json", str(plan_full),
        "--no-confirm",
    ])
    
    # 在目标目录创建同名文件
    target_photo_dir = target_dir / "Photos" / "Personal"
    target_photo_dir.mkdir(parents=True, exist_ok=True)
    existing_file = target_photo_dir / "Screenshot_2024.png"
    with open(existing_file, "wb") as f:
        f.write(b"existing content")
    print(f"创建已存在文件: {existing_file}")
    
    # 执行计划
    report_md6 = base_dir / "report_test6.md"
    report_json6 = base_dir / "report_test6.json"
    
    code, out, err = run_cmd([
        sys.executable, "-m", "file_organizer.cli",
        "move",
        "--plan-file", str(plan_full),
        "--simulate",
        "--yes",
        "--report", str(report_md6),
        "--report-json", str(report_json6),
    ])
    assert code == 0, f"move 失败: {err}"
    
    # 检查终端输出
    print(f"终端输出:")
    print(out[-600:] if len(out) > 600 else out)
    
    assert "自动重命名" in out, f"自动重命名未显示: {out}"
    
    # 检查报告一致性
    json_data6 = check_report_consistency(report_md6, report_json6, {
        "success": 8,  # 全部成功，1个自动改名
        "skipped": 0,
        "failed": 0
    })
    
    # 检查成功明细中是否有自动重命名的文件
    success_details = json_data6["details"]["successful"]
    renamed_file = None
    for item in success_details:
        if item.get("note") and "自动重命名" in item["note"]:
            renamed_file = item
            break
    
    assert renamed_file is not None, "成功明细中没有自动重命名的文件"
    assert "Screenshot_2024.png" in renamed_file["source"], "自动重命名的文件不正确"
    assert "Screenshot_2024_1.png" in renamed_file["destination"], "新文件名不正确"
    print(f"自动重命名: {renamed_file['source']} -> {renamed_file['destination']}")
    print(f"备注: {renamed_file['note']}")
    
    # 检查 Markdown
    with open(report_md6, 'r', encoding='utf-8') as f:
        md6 = f.read()
    assert "自动重命名的文件" in md6, "Markdown 中缺少自动重命名部分"
    assert "Screenshot_2024.png" in md6, "Markdown 中缺少原文件名"
    assert "Screenshot_2024_1.png" in md6, "Markdown 中缺少新文件名"
    
    print("[PASS] 目标文件冲突自动改名 - 报告一致性校验通过")
    
    print("\n" + "="*70)
    print("所有测试通过!")
    print("="*70)
    
    print(f"\n测试目录保留: {base_dir}")
    print(f"报告文件:")
    for f in sorted(base_dir.glob("*.json")):
        print(f"  - {f.name}")
    for f in sorted(base_dir.glob("*.md")):
        print(f"  - {f.name}")

if __name__ == "__main__":
    main()
