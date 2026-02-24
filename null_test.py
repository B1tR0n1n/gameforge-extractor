import json

# Simulate what Claude returns — including nulls that caused the crash
fake_rules = [
    {"type": "rule", "category": "combat", "title": "Cover", "section_number": "6.2",
     "rule_references": ["6.1", "6.3"], "table_references": None, "steps": None,
     "conditions": None, "modifiers": None, "tags": ["cover"], "page": 42,
     "summary": "test", "full_text": "test"},
    {"type": "procedure", "category": "setup", "title": "Setup",
     "section_number": None, "rule_references": None, "table_references": ["Setup Table"],
     "steps": ["step 1"], "conditions": None, "modifiers": None, "tags": None,
     "page": 3, "summary": "test", "full_text": "test"},
]

# This is the fixed post-processing
section_to_id = {"6.1": "fof_combat_001", "6.3": "fof_combat_003"}

for rule in fake_rules:
    resolved = []
    for ref in (rule.get("rule_references") or []):
        if ref in section_to_id:
            resolved.append(section_to_id[ref])
        else:
            resolved.append(ref)
    rule["resolved_references"] = resolved
    for key in ["steps", "conditions", "modifiers", "table_references", "rule_references", "tags"]:
        if rule.get(key) is None:
            rule[key] = []

result = {"game": "test", "total_rules": len(fake_rules), "rules": fake_rules}
json.dump(result, open("null_test.json", "w", encoding="utf-8"), indent=2)
print("PASS — saved clean with null fields handled")
for r in fake_rules:
    print(f"  {r['title']}: refs={r['resolved_references']}, tags={r['tags']}, steps={r['steps']}")
