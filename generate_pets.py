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

# Cat color variants: outline/fur pairs (others stay the same)
CAT_COLOR_SCHEMES: dict[str, dict[str, str]] = {
    # Black cat
    "black": {
        "outline": "#222222",
        "fur": "#3b3b3b",
    },
    # Grey cat
    "grey": {
        "outline": "#555555",
        "fur": "#bdbdbd",
    },
    # White cat
    "white": {
        "outline": "#777777",
        "fur": "#ffffff",
    },
    # Siamese cat
    "siamese": {
        "outline": "#6d4c41",
        "fur": "#f5e0c3",
    },
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
    color_scheme: dict[str, str] | None = None,
) -> str:
    """
    Embed a cat SVG at (x, y) with:
    - repo name label above the cat
    - slow up-down hover animation on the cat
    - level label below the cat
    - optional color scheme applied via CSS variables
    """
    raw_svg = re.sub(r'<\?xml[^?]*\?>', '', raw_svg).strip()

    # If a color scheme is provided, override the outline/fur CSS variables
    if color_scheme is not None:
        outline = color_scheme.get("outline")
        fur = color_scheme.get("fur")
        if outline:
            raw_svg = re.sub(
                r"--outline:\s*#[0-9A-Fa-f]{3,6}",
                f"--outline: {outline}",
                raw_svg,
            )
        if fur:
            raw_svg = re.sub(
                r"--fur:\s*#[0-9A-Fa-f]{3,6}",
                f"--fur: {fur}",
                raw_svg,
            )

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
        f'    <g transform="scale({scale:.4f})">{inner}</g>\n'
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

    all_variants = list(CAT_COLOR_SCHEMES.keys())

    for i, pet in enumerate(pets):
        col = i % cols
        row = i // cols
        x   = PADDING + col * (PET_W + PADDING)
        y   = PADDING + row * (cell_h + PADDING)

        variant      = random.choice(all_variants)
        color_scheme = CAT_COLOR_SCHEMES[variant]

        parts.append(
            embed_svg(
                cat_svg,
                x,
                y,
                pet["name"],
                level=pet.get("commits"),
                color_scheme=color_scheme,
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
