from pathlib import Path
text = Path('templates/stipendi.html').read_text(encoding='latin-1')
coords = [(idx, ch) for idx, ch in enumerate(text) if ord(ch) > 127]
print(len(coords))
print(coords[:20])
