import json
d = json.load(open('FoF_extracted.json', 'r', encoding='utf-8'))
for p in d['pages'][:15]:
    blocks = p.get('blocks', p.get('text_blocks', []))
    if blocks:
        print(f"Page {p['pageNumber']}:")
        for b in blocks[:3]:
            print(f"  [{b['blockType']}] {b['text'][:80]}")
        print()
