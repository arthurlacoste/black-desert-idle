#!/usr/bin/env python3
"""
Build local pour Black Desert Idle (2026-07-08).

Ce script fait donc :
  1. lit l'ordre exact des <script src="src/..."> dans index.dev.html (source de verite
     unique pour l'ordre de dependance, voir CLAUDE.md, section chargement) ;
  2. concatene ces fichiers dans cet ordre, en retirant les commentaires JS (// et /* */)
     via un mini-analyseur caractere par caractere qui respecte les chaines/template
     literals (y compris ${...} imbriques), pas une regex naive qui casserait toute
     chaine contenant "//" (URLs, etc.) ;
  3. compacte les lignes vides ;
  4. ecrit le bundle lisible dans build/source.js ;
  5. minifie avec Terser dans build/source.min.js : compression + variables locales raccourcies,
     sans toplevel et sans mangle-props pour garder les globals, proprietes, callbacks, RPC SQL
     et appels Supabase intacts ;
  6. reecrit index.html pour charger build/source.min.js.

Usage : python scripts/build.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_HTML = ROOT / "index.dev.html"
PROD_HTML = ROOT / "index.html"
BUILD_DIR = ROOT / "build"
BUNDLE_PATH = BUILD_DIR / "source.js"
MINIFIED_BUNDLE_PATH = BUILD_DIR / "source.min.js"

# fichiers explicitement exclus du bundle prod meme s'ils apparaissent dans index.dev.html
EXCLUDED_SUBSTRINGS = ("tests/tests.js", "meta/patch-notes-data.js", "supabase-js")


def extract_script_order(html_text):
    """Ordre exact des <script src="src/..."> dans index.dev.html, dans l'ordre du document."""
    srcs = re.findall(r'<script src="([^"]+)"', html_text)
    ordered = []
    for src in srcs:
        if any(x in src for x in EXCLUDED_SUBSTRINGS):
            continue
        if not src.startswith("src/"):
            continue  # garde-fou : ne prend que les fichiers de gameplay sous src/
        path = src.split("?")[0]  # retire le ?v=XXX
        ordered.append(path)
    return ordered


def strip_js_comments_safe(code):
    """
    Analyseur caractere par caractere (pas une regex naive) : retire les commentaires
    // et /* */ en dehors des chaines/template literals. Les ${...} a l'interieur d'un
    template literal sont traites comme du VRAI code JS (via scan_expr, recursif sur les
    accolades), donc leurs propres chaines/commentaires sont geres correctement -- sans
    ca, un commentaire ou un guillemet a l'interieur d'un ${...} casserait le reste du
    fichier.
    """
    out = []
    i, n = 0, len(code)

    def scan(i, in_template):
        """Retourne (texte_nettoye, nouvel_index) ; s'arrete a la fin du fichier, ou si
        in_template est vrai, a la fin du template literal (backtick fermant)."""
        buf = []
        while i < n:
            c = code[i]
            two = code[i:i + 2]
            if two == "//" and not in_template:
                j = code.find("\n", i)
                i = n if j == -1 else j
                continue
            if two == "/*" and not in_template:
                j = code.find("*/", i + 2)
                i = n if j == -1 else j + 2
                continue
            if c in ("'", '"') and not in_template:
                buf.append(c)
                i += 1
                start_quote = c
                while i < n:
                    if code[i] == "\\" and i + 1 < n:
                        buf.append(code[i:i + 2])
                        i += 2
                        continue
                    buf.append(code[i])
                    if code[i] == start_quote:
                        i += 1
                        break
                    i += 1
                continue
            if not in_template and c == "`":
                buf.append(c)
                i += 1
                inner, i = scan(i, in_template=True)
                buf.append(inner)
                continue
            if in_template and c == "\\" and i + 1 < n:
                buf.append(code[i:i + 2])
                i += 2
                continue
            if in_template and two == "${":
                buf.append("${")
                i += 2
                inner, i = scan_expr(i)
                buf.append(inner)
                continue
            if in_template and c == "`":
                buf.append(c)
                i += 1
                return "".join(buf), i
            buf.append(c)
            i += 1
        return "".join(buf), i

    def scan_expr(i):
        """Scanne le contenu d'un ${...} (du vrai code) jusqu'a l'accolade fermante
        correspondante (profondeur d'accolades), puis consomme le '}'."""
        buf = []
        depth = 1
        while i < n:
            c = code[i]
            two = code[i:i + 2]
            if two == "//":
                j = code.find("\n", i)
                i = n if j == -1 else j
                continue
            if two == "/*":
                j = code.find("*/", i + 2)
                i = n if j == -1 else j + 2
                continue
            if c in ("'", '"'):
                buf.append(c)
                i += 1
                start_quote = c
                while i < n:
                    if code[i] == "\\" and i + 1 < n:
                        buf.append(code[i:i + 2])
                        i += 2
                        continue
                    buf.append(code[i])
                    if code[i] == start_quote:
                        i += 1
                        break
                    i += 1
                continue
            if c == "`":
                buf.append(c)
                i += 1
                inner, i = scan(i, in_template=True)
                buf.append(inner)
                continue
            if c == "{":
                depth += 1
                buf.append(c)
                i += 1
                continue
            if c == "}":
                depth -= 1
                if depth == 0:
                    buf.append(c)
                    i += 1
                    return "".join(buf), i
                buf.append(c)
                i += 1
                continue
            buf.append(c)
            i += 1
        return "".join(buf), i

    text, _ = scan(0, in_template=False)
    return text


def compact_blank_lines(code):
    lines = code.split("\n")
    out = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        out.append(line)
    return "\n".join(out)


def format_bytes(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} Mo"
    if size >= 1024:
        return f"{size / 1024:.1f} Ko"
    return f"{size} o"


def minify_bundle_with_terser():
    """Minifie avec Terser. Safe mode : pas de toplevel, pas de mangle-props.
    Les fonctions globales, noms de proprietes, strings RPC SQL et appels Supabase restent stables.
    """
    cmd = [
        "npx",
        "--no-install",
        "terser",
        str(BUNDLE_PATH),
        "--compress",
        "passes=2",
        "--mangle",
        "--output",
        str(MINIFIED_BUNDLE_PATH),
    ]
    try:
        subprocess.run(cmd, cwd=ROOT, check=True)
    except FileNotFoundError:
        print("ERREUR: npx introuvable. Lance npm install, puis relance npm run build.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print("ERREUR: Terser a echoue. Lance npm install, puis relance npm run build.", file=sys.stderr)
        sys.exit(exc.returncode)



def print_size_report(total_source_bytes, stripped_bytes):
    readable_size = BUNDLE_PATH.stat().st_size
    minified_size = MINIFIED_BUNDLE_PATH.stat().st_size
    stripped_pct = 100 * (1 - stripped_bytes / total_source_bytes) if total_source_bytes else 0
    min_pct = 100 * (1 - minified_size / readable_size) if readable_size else 0

    print(f"\nbuild/source.js genere : {format_bytes(total_source_bytes)} -> {format_bytes(stripped_bytes)} ({stripped_pct:.1f}% de reduction)")
    print(f"build/source.min.js genere : {format_bytes(readable_size)} -> {format_bytes(minified_size)} ({min_pct:.1f}% de reduction)")


def main():
    if not DEV_HTML.exists():
        print(f"ERREUR: {DEV_HTML} introuvable", file=sys.stderr)
        sys.exit(1)

    dev_html = DEV_HTML.read_text(encoding="utf-8")
    files = extract_script_order(dev_html)
    if not files:
        print("ERREUR: aucun script src/... trouve dans index.dev.html", file=sys.stderr)
        sys.exit(1)

    print(f"{len(files)} fichiers a bundler, dans cet ordre :")
    for f in files:
        print(f"  - {f}")

    parts = []
    total_before, total_after = 0, 0
    for rel_path in files:
        full_path = ROOT / rel_path
        if not full_path.exists():
            print(f"ERREUR: {full_path} introuvable", file=sys.stderr)
            sys.exit(1)
        src = full_path.read_text(encoding="utf-8")
        total_before += len(src)
        stripped = strip_js_comments_safe(src)
        stripped = compact_blank_lines(stripped)
        total_after += len(stripped)
        parts.append(f"// ==== {rel_path} ====\n{stripped.strip()}\n")

    bundle = "\n".join(parts)
    BUILD_DIR.mkdir(exist_ok=True)
    BUNDLE_PATH.write_text(bundle, encoding="utf-8", newline="\n")
    minify_bundle_with_terser()
    print_size_report(total_before, total_after)

    rewrite_prod_html(dev_html)
    print("index.html (prod) reecrit pour charger build/source.min.js")


def rewrite_prod_html(dev_html):
    """Reconstruit index.html a partir de index.dev.html, ligne par ligne :
      - chaque <script src="src/...  -> retiree ; une seule balise vers le bundle minifie est inseree
        a la position de la premiere d'entre elles ;
      - <script src="meta/patch-notes-data.js...> -> conservee telle quelle, avant le bundle ;
      - <script src="tests/tests.js...> -> retiree entierement, jamais chargee en prod."""
    m = re.search(r"\?v=(\d+)", dev_html)
    version = m.group(1) if m else "1"

    lines = dev_html.split("\n")
    # meta/patch-notes-data.js doit charger AVANT le bundle (CURRENT_VERSION = PATCH_NOTES[0].v
    # est lu au top-level dans game-supabase.js, qui fait partie du bundle) -- quelle que soit sa
    # position d'origine dans index.dev.html (au milieu de la liste src/), sa balise est extraite
    # et reinseree juste avant la balise du bundle.
    meta_lines = [ln for ln in lines if re.search(r'<script src="meta/', ln)]

    prod_lines = []
    bundle_tag_inserted = False
    for line in lines:
        if re.search(r'<script src="(src/|meta/)', line):
            if not bundle_tag_inserted:
                prod_lines.extend(meta_lines)
                prod_lines.append(f'<script src="build/source.min.js?v={version}"></script>')
                bundle_tag_inserted = True
            continue  # les autres balises src/|meta/ sont sautees (deja placees ci-dessus)
        if re.search(r'<script src="tests/tests\.js', line):
            continue  # jamais charge en prod
        prod_lines.append(line)

    if not bundle_tag_inserted:
        raise RuntimeError("aucune balise <script src=\"src/...\"> trouvee dans index.dev.html")

    PROD_HTML.write_text("\n".join(prod_lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
