import os
import random
import re
import requests

# ── Configuration ─────────────────────────────────────────────────────────────

GITHUB_TOKEN = os.environ["GH_PAT"]
USERNAME     = os.environ["GH_USERNAME"]

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# SVG asset
ASSETS_DIR   = "assets"
CAT_SVG_PATH = os.path.join(ASSETS_DIR, "cat.svg")

# Layout
PET_W         = 120
PET_H         = 120
PETS_PER_ROW  = 5
PADDING       = 16
NAME_LABEL_H  = 20   # space above cat for repo name
LEVEL_LABEL_H = 20   # space below cat for level

# Cat color variants: filter_id -> SVG filter primitives (None = original orange, no filter)
CAT_COLOR_FILTERS: dict[str, str | None] = {
    "orange": None,
    "gray": (
        '<feColorMatrix type="saturate" values="0"/>'
    ),
    "brown": (
        '<feColorMatrix type="hueRotate" values="-20"/>'
        '<feColorMatrix type="saturate" values="0.5"/>'
        '<feComponentTransfer>'
        '<feFuncR type="linear" slope="0.85"/>'
        '<feFuncG type="linear" slope="0.72"/>'
        '<feFuncB type="linear" slope="0.60"/>'
        '</feComponentTransfer>'
    ),
    "black": (
        '<feColorMatrix type="saturate" values="0"/>'
        '<feComponentTransfer>'
        '<feFuncR type="linear" slope="0.22"/>'
        '<feFuncG type="linear" slope="0.22"/>'
        '<feFuncB type="linear" slope="0.22"/>'
        '</feComponentTransfer>'
    ),
    "cream": (
        '<feColorMatrix type="saturate" values="0.25"/>'
        '<feComponentTransfer>'
        '<feFuncR type="linear" slope="1.05" intercept="0.06"/>'
        '<feFuncG type="linear" slope="0.95" intercept="0.03"/>'
        '<feFuncB type="linear" slope="0.80"/>'
        '</feComponentTransfer>'
    ),
    "red": (
        '<feColorMatrix type="hueRotate" values="-30"/>'
        '<feColorMatrix type="saturate" values="1.2"/>'
    ),
}

# ── Load SVG file ──────────────────────────────────────────────────────────────

def load_cat_svg() -> str:
    if not os.path.exists(CAT_SVG_PATH):
        raise FileNotFoundError(f"Missing cat SVG at {CAT_SVG_PATH}")
    with open(CAT_SVG_PATH, "r") as f:
        return f.read().strip()


def embed_svg(
    raw_svg: str,
    x: int,
    y: int,
    name: str,
    level: int | None = None,
    filter_id: str | None = None,
) -> str:
    """
    Embed a cat SVG at (x, y) with:
    - repo name label above the cat
    - slow up-down hover animation on the cat
    - level label below the cat
    """
    raw_svg = re.sub(r'<\?xml[^?]*\?>', '', raw_svg).strip()

    svg_open_end = raw_svg.index(">") + 1
    svg_close    = raw_svg.rindex("</svg>")
    inner        = raw_svg[svg_open_end:svg_close].strip()

    vb          = re.search(r'viewBox=["\']([^"\']+)["\']', raw_svg)
    width_attr  = re.search(r'\bwidth=["\']([^"\'px]+)["\']', raw_svg)
    height_attr = re.search(r'\bheight=["\']([^"\'px]+)["\']', raw_svg)

    if vb:
        parts  = vb.group(1).split()
        orig_w = float(parts[2])
        orig_h = float(parts[3])
    elif width_attr and height_attr:
        orig_w = float(width_attr.group(1))
        orig_h = float(height_attr.group(1))
    else:
        orig_w = orig_h = 100.0

    scale = min(PET_W / orig_w, PET_H / orig_h)

    filter_attr = f' filter="url(#{filter_id})"' if filter_id else ""
    short_name  = name if len(name) <= 14 else name[:13] + "…"

    # Randomise duration and start offset so cats don't all hover in sync
    anim_dur   = round(random.uniform(2.5, 4.0), 2)
    anim_begin = round(random.uniform(0.0, 2.0), 2)

    cat_y      = NAME_LABEL_H
    level_text = f"Lv {level}" if level is not None else ""

    return (
        f'<g transform="translate({x},{y})">\n'
        # ── Name above ──
        f'  <text x="{PET_W // 2}" y="14" text-anchor="middle" '
        f'font-size="7.5" fill="#bbb" font-family="monospace">{short_name}</text>\n'
        # ── Hovering cat ──
        f'  <g transform="translate(0,{cat_y})">\n'
        f'    <animateTransform attributeName="transform" type="translate" '
        f'additive="sum" values="0,0; 0,-5; 0,0" dur="{anim_dur}s" '
        f'begin="{anim_begin}s" repeatCount="indefinite" calcMode="spline" '
        f'keySplines="0.45 0 0.55 1; 0.45 0 0.55 1"/>\n'
        f'    <g transform="scale({scale:.4f})"{filter_attr}>{inner}</g>\n'
        f'  </g>\n'
        # ── Level below (fixed — does not oscillate) ──
        f'  <text x="{PET_W // 2}" y="{cat_y + PET_H + 14}" text-anchor="middle" '
        f'font-size="7.5" fill="#bbb" font-family="monospace">{level_text}</text>\n'
        f'</g>'
    )

# ── GitHub API helpers ─────────────────────────────────────────────────────────

def get_all_repos() -> list[dict]:
    """Return all non-fork repos owned by the authenticated user."""
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=HEADERS,
            params={"type": "owner", "per_page": 100, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(b for b in batch if not b["fork"])
        page += 1
    return repos


def get_commit_count(repo_full_name: str) -> int:
    """Return total commit count for the repo's default branch."""
    r = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/commits",
        headers=HEADERS,
        params={"per_page": 1},
    )
    if r.status_code == 409:   # empty repo
        return 0
    r.raise_for_status()

    link = r.headers.get("Link", "")
    if 'rel="last"' in link:
        last_part = [p for p in link.split(",") if 'rel="last"' in p][0]
        return int(last_part.split("page=")[-1].split(">")[0])

    all_r = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/commits",
        headers=HEADERS,
        params={"per_page": 100},
    )
    all_r.raise_for_status()
    return len(all_r.json())

# ── SVG assembly ──────────────────────────────────────────────────────────────

def build_combined_svg(pets: list[dict], cat_svg: str) -> str:
    if not pets:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50">'
            '<text x="10" y="30" font-family="monospace" font-size="12" fill="#888">'
            'No repos found.</text></svg>'
        )

    cols    = min(len(pets), PETS_PER_ROW)
    rows    = (len(pets) + cols - 1) // cols
    cell_h  = NAME_LABEL_H + PET_H + LEVEL_LABEL_H
    total_w = cols * PET_W + (cols + 1) * PADDING
    total_h = rows * cell_h + (rows + 1) * PADDING

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}">',
        f'<rect width="{total_w}" height="{total_h}" fill="#0d1117" rx="12"/>',
    ]

    # Emit filter defs for each color variant
    defs_parts = ["<defs>"]
    for variant, primitives in CAT_COLOR_FILTERS.items():
        if primitives is not None:
            defs_parts.append(f'<filter id="cat-{variant}">{primitives}</filter>')
    defs_parts.append("</defs>")
    parts.extend(defs_parts)

    all_variants = list(CAT_COLOR_FILTERS.keys())

    for i, pet in enumerate(pets):
        col = i % cols
        row = i // cols
        x   = PADDING + col * (PET_W + PADDING)
        y   = PADDING + row * (cell_h + PADDING)

        variant   = random.choice(all_variants)
        filter_id = f"cat-{variant}" if CAT_COLOR_FILTERS[variant] is not None else None

        parts.append(
            embed_svg(
                cat_svg,
                x,
                y,
                pet["name"],
                level=pet.get("commits"),
                filter_id=filter_id,
            )
        )

    parts.append("</svg>")
    return "\n".join(parts)

# ── Main ──────────────────────────────────────────────────────────────────────

def main(output_path: str = "pets.svg") -> None:
    cat_svg = load_cat_svg()
    print("✅ Loaded cat SVG")

    print(f"👤 Fetching repos for: {USERNAME}")
    repos = get_all_repos()
    print(f"📦 Found {len(repos)} non-fork repos")

    pets = []
    for repo in repos:
        name = repo["name"]
        if name == USERNAME:   # skip the profile repo itself
            continue
        count = get_commit_count(repo["full_name"])
        print(f"  {name}: {count} commits")
        pets.append({"name": name, "commits": count})

    pets.sort(key=lambda p: p["name"])

    svg = build_combined_svg(pets, cat_svg)
    with open(output_path, "w") as f:
        f.write(svg)

    print(f"✅ Saved {len(pets)} pets → {output_path}")


if __name__ == "__main__":
    main()
