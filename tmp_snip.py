from pathlib import Path
text = Path('templates/stipendi.html').read_text(encoding='latin-1')
coords = [2798, 17372, 17473, 17564]
for idx in coords:
    start = max(0, idx-60)
    end = idx+60
    snippet = text[start:end]
    print('---', idx, '---')
    print(snippet.encode('unicode_escape').decode('ascii'))
