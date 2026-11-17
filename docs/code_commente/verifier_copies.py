"""Check that each annotated copy has exactly the same code as its original.

Usage (from the repo root):  python docs/code_commente/verifier_copies.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "code_commente"
ok = True


def sql_code(text: str) -> str:
    text = re.sub(r"--[^\n]*", "", text)          # drop -- comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return " ".join(text.split())                 # normalise whitespace


for ann in sorted(DOC.rglob("*")):
    if ann.suffix not in {".py", ".sql"} or ann.name == "verifier_copies.py":
        continue
    orig = ROOT / ann.relative_to(DOC)
    if not orig.exists():
        print(f"NO ORIGINAL  {ann.relative_to(DOC)}"); ok = False; continue
    a, o = ann.read_text(), orig.read_text()
    if ann.suffix == ".py":
        same = ast.dump(ast.parse(a)) == ast.dump(ast.parse(o))
    else:
        same = sql_code(a) == sql_code(o)
    n_code = sum(1 for l in o.splitlines() if l.strip() and not l.strip().startswith(("#", "--")))
    n_com = sum(1 for l in a.splitlines() if l.strip().startswith(("#", "--")))
    print(f"{'OK ' if same else 'DIFF'}  {str(ann.relative_to(DOC)):45s} code lines {n_code:4d} | FR comment lines {n_com:4d}")
    ok &= same

originals = [p for p in list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
             + list((ROOT / "dbt" / "models").rglob("*.sql")) if p.name != "__init__.py"]
missing = [p.relative_to(ROOT) for p in originals if not (DOC / p.relative_to(ROOT)).exists()]
print("Missing annotated copies:", [str(m) for m in missing] or "none")
sys.exit(0 if ok else 1)
