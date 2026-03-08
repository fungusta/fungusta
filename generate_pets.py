import os
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

# Commit count → pet stage thresholds (3 stages)
STAGES = [
    (0,   50,  "baby"),
    (51,  200, "teen"),
    (201, None,"adult"),
]

# SVG asset paths
ASSETS_DIR = "assets"
STAGE_SVG: dict[str, str] = {
    "baby":  os.path.join(ASSETS_DIR, "baby.svg"),
    "teen":  os.path.join(ASSETS_DIR, "teen.svg"),
    "adult": os.path.join(ASSETS_DIR, "adult.svg"),
}

# Layout
PET_W        = 120
PET_H        = 120
PETS_PER_ROW = 5
PADDING      = 16
LABEL_H      = 20   # space reserved below each pet for the repo name

# ── Load SVG files ─────────────────────────────────────────────────────────────

def load_stage_svgs() -> dict[str, str]:
    """Read each stage SVG from disk and return raw SVG content keyed by stage."""
    svgs = {}
    for stage, path in STAGE_SVG.items():
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing SVG for stage '{stage}': expected at {path}\n"
                f"Please add your SVG files to the '{ASSETS_DIR}/' folder."
            )
        with open(path, "r") as f:
            svgs[stage] = f.read().strip()
    return svgs


def embed_svg(raw_svg: str, x: int, y: int, label: str) -> str:
    """
    Wrap a raw SVG into a <g> positioned at (x, y), scaled to PET_W x PET_H,
    and append a repo name label beneath it.
    """
    # Strip XML declaration
    raw_svg = re.sub(r'<\?xml[^?]*\?>', '', raw_svg).strip()

    # Extract inner content (everything between the outer <svg> tags)
    svg_open_end = raw_svg.index(">") + 1
    svg_close    = raw_svg.rindex("</svg>")
    inner        = raw_svg[svg_open_end:svg_close].strip()

    # Derive original dimensions for scaling
    vb         = re.search(r'viewBox=["\']([^"\']+)["\']', raw_svg)
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
        orig_w = orig_h = 100.0   # safe fallback

    scale = min(PET_W / orig_w, PET_H / orig_h)

    short_label = label if len(label) <= 14 else label[:13] + "…"
    label_y     = PET_H + 14

    return (
        f'<g transform="translate({x},{y})">\n'
        f'  <g transform="scale({scale:.4f})">{inner}</g>\n'
        f'  <text x="{PET_W // 2}" y="{label_y}" text-anchor="middle" '
        f'font-size="7.5" fill="#bbb" font-family="monospace">{short_label}</text>\n'
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

    # Fewer than per_page=1 result → fetch all and count
    all_r = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/commits",
        headers=HEADERS,
        params={"per_page": 100},
    )
    all_r.raise_for_status()
    return len(all_r.json())


def get_stage(commit_count: int) -> str:
    for _low, high, stage in STAGES:
        if high is None or commit_count <= high:
            return stage
    return "adult"

# ── SVG assembly ──────────────────────────────────────────────────────────────

def build_combined_svg(pets: list[dict], stage_svgs: dict[str, str]) -> str:
    if not pets:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50">'
            '<text x="10" y="30" font-family="monospace" font-size="12" fill="#888">'
            'No repos found.</text></svg>'
        )

    cols    = min(len(pets), PETS_PER_ROW)
    rows    = (len(pets) + cols - 1) // cols
    cell_h  = PET_H + LABEL_H
    total_w = cols * PET_W + (cols + 1) * PADDING
    total_h = rows * cell_h + (rows + 1) * PADDING

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}">',
        f'<rect width="{total_w}" height="{total_h}" fill="#0d1117" rx="12"/>',
    ]

    for i, pet in enumerate(pets):
        col = i % cols
        row = i // cols
        x   = PADDING + col * (PET_W + PADDING)
        y   = PADDING + row * (cell_h  + PADDING)
        parts.append(embed_svg(stage_svgs[pet["stage"]], x, y, pet["name"]))

    parts.append("</svg>")
    return "\n".join(parts)

# ── Main ──────────────────────────────────────────────────────────────────────

def main(output_path: str = "pets.svg") -> None:
    stage_svgs = load_stage_svgs()
    print(f"✅ Loaded stage SVGs: {list(stage_svgs.keys())}")

    print(f"👤 Fetching repos for: {USERNAME}")
    repos = get_all_repos()
    print(f"📦 Found {len(repos)} non-fork repos")

    pets = []
    for repo in repos:
        name = repo["name"]
        if name == USERNAME:   # skip the profile repo itself
            continue
        count = get_commit_count(repo["full_name"])
        stage = get_stage(count)
        print(f"  {name}: {count} commits → {stage}")
        pets.append({"name": name, "stage": stage})

    # Sort: most evolved first, then alphabetical within stage
    stage_order = {"adult": 0, "teen": 1, "baby": 2}
    pets.sort(key=lambda p: (stage_order[p["stage"]], p["name"]))

    svg = build_combined_svg(pets, stage_svgs)
    with open(output_path, "w") as f:
        f.write(svg)

    print(f"✅ Saved {len(pets)} pets → {output_path}")


if __name__ == "__main__":
    main()
