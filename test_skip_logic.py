import json
from pathlib import Path

print("=" * 70)
print("测试计划 JSON 跳过逻辑")
print("=" * 70)

# 1. 读取原始计划
with open('plan_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"\n原始计划:")
print(f"  总文件数: {len(data['actions'])}")
print(f"  分类: {list(data['categories'].keys())}")
for cat, cat_data in data['categories'].items():
    if isinstance(cat_data, dict):
        print(f"    {cat}: {cat_data['count']} 个, skipped={cat_data.get('skipped', False)}")

# 2. 测试 1: 只修改分类级 skipped
print(f"\n{'=' * 70}")
print("测试 1: 分类级跳过 (other 分类 skipped=true)")
print("=" * 70)
data1 = json.loads(json.dumps(data))
data1['categories']['other']['skipped'] = True

with open('plan_test_skip_cat.json', 'w', encoding='utf-8') as f:
    json.dump(data1, f, ensure_ascii=False, indent=2)

# 3. 测试 2: 只修改文件级 skipped
print(f"\n{'=' * 70}")
print("测试 2: 文件级跳过 (跳过 code 分类下第一个文件)")
print("=" * 70)
data2 = json.loads(json.dumps(data))
code_actions = data2['categories']['code']['actions']
if code_actions:
    skip_file = code_actions[0]['source']
    code_actions[0]['skipped'] = True
    # 同时修改顶层 actions
    for a in data2['actions']:
        if a['source'] == skip_file:
            a['skipped'] = True
            print(f"  跳过文件: {skip_file}")
            break

with open('plan_test_skip_file.json', 'w', encoding='utf-8') as f:
    json.dump(data2, f, ensure_ascii=False, indent=2)

# 4. 测试 3: 同时修改分类和文件
print(f"\n{'=' * 70}")
print("测试 3: 同时跳过分类和文件")
print("=" * 70)
data3 = json.loads(json.dumps(data))
# 跳过 work_documents 分类
data3['categories']['work_documents']['skipped'] = True
print(f"  跳过分类: work_documents")

# 跳过 personal_photos 下的一个文件
photo_actions = data3['categories']['personal_photos']['actions']
if photo_actions:
    skip_file = photo_actions[0]['source']
    photo_actions[0]['skipped'] = True
    for a in data3['actions']:
        if a['source'] == skip_file:
            a['skipped'] = True
            print(f"  跳过文件: {skip_file}")
            break

with open('plan_test_skip_both.json', 'w', encoding='utf-8') as f:
    json.dump(data3, f, ensure_ascii=False, indent=2)

print(f"\n测试文件已创建:")
print(f"  1. plan_test_skip_cat.json   - 只跳过分类")
print(f"  2. plan_test_skip_file.json  - 只跳过文件")
print(f"  3. plan_test_skip_both.json  - 同时跳过")
print(f"\n接下来使用 move --plan-file 测试...")
