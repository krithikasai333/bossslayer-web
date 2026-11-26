"""
Draw every SMILES in chapters.json with RDKit and save the drawings.

Usage (run in the folder that holds index.html and chapters.json):

    pip install -r requirements.txt
    python draw_structures.py            # draw + write chapters.json and index.html
    python draw_structures.py --check    # only validate every SMILES, write nothing

What it does
  * Adds an "svg" field to each question that has a "smiles" string.
  * Refreshes the built-in copy of the chapters (const EMBEDDED = ...) inside index.html.
  * Leaves questions with an "image" field (scanned paper figures) alone.
  * Leaves questions without a "smiles" string alone (so a hand-made "svg" survives).
  * If ANY smiles cannot be parsed, it lists every bad one (question id + string),
    exits with status 1 and writes nothing, so a typo never half-updates your files.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from rdkit import Chem, rdBase
    from rdkit.Chem.Draw import rdMolDraw2D
except ImportError:
    sys.exit("RDKit is not installed. Run:  pip install -r requirements.txt")

WIDTH, HEIGHT = 260, 140
HERE = Path(__file__).resolve().parent
CHAPTERS = HERE / "chapters.json"
INDEX = HERE / "index.html"

# The whole EMBEDDED declaration sits on one line of index.html and ends with ";".
EMBEDDED_RE = re.compile(r"^const EMBEDDED = .*;$", re.M)


def iter_questions(chapters):
    """Yield every question, including those inside nested subTopics."""
    for chapter in chapters:
        for q in chapter.get("questions", []):
            yield q
        yield from iter_questions(chapter.get("subTopics", []))


def smiles_to_svg(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("RDKit could not parse this SMILES")
    drawer = rdMolDraw2D.MolDraw2DSVG(WIDTH, HEIGHT)
    opts = drawer.drawOptions()
    opts.useBWAtomPalette()          # dark ink on white
    opts.padding = 0.08
    # "*" (for example in CC(C)(C)*) is an attachment point, so draw it as a bond
    # that leads off the structure instead of a literal "*" atom.
    if hasattr(opts, "dummiesAreAttachments"):
        opts.dummiesAreAttachments = True
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)   # XML declaration is illegal inside HTML
    svg = re.sub(r"<!--.*?-->\s*", "", svg, flags=re.S)  # drop comments (less churn between versions)
    return svg.strip()


def report(errors):
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    print(f"\n{len(errors)} problem(s) found in chapters.json:", file=sys.stderr)
    for qid, smi, why in errors:
        print(f"  - {qid}: {smi!r}  ->  {why}", file=sys.stderr)
        if on_github:
            print(f"::error file=chapters.json,title=Bad SMILES::{qid}: {smi!r} ({why})")


def embed(data):
    """Return the one-line JS declaration for index.html."""
    payload = json.dumps(data, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")   # a stray "</script" can never end the script block
    return "const EMBEDDED = " + payload + ";"


def write_if_changed(path, text):
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="validate every SMILES and exit; write nothing")
    args = parser.parse_args()

    print(f"RDKit {rdBase.rdkitVersion}")
    data = json.loads(CHAPTERS.read_text(encoding="utf-8"))

    errors, drawn, skipped_images = [], 0, 0
    for q in iter_questions(data["chapters"]):
        smi = q.get("smiles")
        if q.get("image"):
            skipped_images += 1
            continue
        if smi is None or (isinstance(smi, str) and not smi.strip()):
            continue
        qid = q.get("id", "<no id>")
        if not isinstance(smi, str):
            errors.append((qid, smi, "smiles must be a string or null"))
            continue
        try:
            q["svg"] = smiles_to_svg(smi.strip())
            drawn += 1
        except Exception as exc:                       # keep going so we report every bad one
            errors.append((qid, smi, str(exc)))

    if errors:
        report(errors)
        sys.exit(1)

    print(f"{drawn} structure(s) OK; {skipped_images} question(s) with a paper figure left alone.")
    if args.check:
        print("--check: nothing written.")
        return

    # Check index.html BEFORE writing anything, so the two files never end up out of sync.
    if not INDEX.exists():
        sys.exit(f"{INDEX.name} not found next to this script")
    html = INDEX.read_text(encoding="utf-8")
    if not EMBEDDED_RE.search(html):
        sys.exit("Could not find the line starting 'const EMBEDDED = ' in index.html; "
                 "nothing was written.")

    chapters_text = json.dumps(data, ensure_ascii=False, indent=2)
    if write_if_changed(CHAPTERS, chapters_text):
        print(f"Updated {CHAPTERS.name}")
    else:
        print(f"{CHAPTERS.name} already up to date")

    new_html = EMBEDDED_RE.sub(lambda _: embed(data), html, count=1)
    if write_if_changed(INDEX, new_html):
        print(f"Refreshed the built-in chapters in {INDEX.name}")
    else:
        print(f"{INDEX.name} already up to date")


if __name__ == "__main__":
    main()
