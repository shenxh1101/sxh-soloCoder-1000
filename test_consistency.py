from pathlib import Path
from file_organizer.rule_manager import RuleManager
from file_organizer.scanner import Scanner
from file_organizer.planner import PlanGenerator

rule_manager = RuleManager()
rules = rule_manager.load_config(Path('my_rules.json'))

print("=" * 70)
print("测试分类一致性 (Screenshot_2024.png)")
print("=" * 70)

# 测试 explain
exp = rules.explain_file('Screenshot_2024.png', '.png')
print(f'\nexplain 结果:')
print(f'  分类: {exp["category"]}')
print(f'  来源: {exp["category_source"]}')
print(f'  目标目录: {exp["target_dir"]}')
print(f'  匹配方式: {exp["match_type"]}')

# 测试 scanner
print(f'\nscan 结果:')
scanner = Scanner(root_dir=Path('test_dir'), rules=rules)
result = scanner.scan()
for f in result.files:
    if f.name == 'Screenshot_2024.png':
        print(f'  分类: {f.category}')
        break

# 测试 planner
print(f'\nplan 结果:')
planner = PlanGenerator(
    scan_result=result,
    target_root=Path('test_target'),
    rules=rules,
)
plan = planner.generate()

# 查找 Screenshot_2024.png 在哪个分类
for cat, actions in plan.categories.items():
    for action in actions:
        if action.source.name == 'Screenshot_2024.png':
            print(f'  分类: {cat}')
            print(f'  目标路径: {action.destination}')
            break

# 测试 classify 方法
print(f'\nclassify 结果:')
cls = rules.classify('Screenshot_2024.png', '.png')
print(f'  分类: {cls["category"]}')
print(f'  来源: {cls["category_source"]}')
print(f'  目标目录: {cls["target_dir"]}')
print(f'  匹配方式: {cls["match_type"]}')

# 检查是否一致
all_match = (exp['category'] == cls['category'])
print(f'\n一致性检查: {"[OK]" if all_match else "[X]"}')
if all_match:
    print('  explain 和 classify 结果一致')
else:
    print(f'  不一致: explain={exp["category"]}, classify={cls["category"]}')
