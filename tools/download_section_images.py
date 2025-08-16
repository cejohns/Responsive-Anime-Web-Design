# tools/download_section_images.py
# Fetches images for Action / Child / Family sections, saves to your repo structure,
# and emits a manifest your frontend can consume.

import os, io, re, json, zipfile, pathlib, time, requests
from PIL import Image
from duckduckgo_search import DDGS

# ---------- Config ----------
ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root (…/Responsive-Anime-Web-Design)
IMG_DIR = ROOT / "img" / "img"   # matches your current structure
OUT_ACTION = IMG_DIR / "movies" / "action"
OUT_CHILD  = IMG_DIR / "movies" / "child"
OUT_FAMILY = IMG_DIR / "movies" / "family"
MANIFEST_DIR = IMG_DIR / "manifest"
MANIFEST_PATH = MANIFEST_DIR / "sections.json"
ZIP_PATH = ROOT / "anime_sections.zip"

# Set this True if you want a ZIP with everything after download
MAKE_ZIP = True

# If you want automatic slider crops (1920x800 center-crop), set True
MAKE_SLIDER_CROPS = False  # you can turn this on later

# Preferred minimum image width/height
MIN_W, MIN_H = 900, 1200  # portrait posters usually tall; relax if needed

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ImageFetcher/1.0)"}

# ---------- Lists ----------
# Use strong search queries to bias toward official key visuals/posters
def q(s): return f"{s} official key visual poster anime"

ACTION = [
    ("Attack on Titan", "Intense action against giant Titans", q("Attack on Titan")),
    ("Demon Slayer", "Young demon slayer's quest", q("Demon Slayer Kimetsu no Yaiba")),
    ("Fullmetal Alchemist", "Brothers using alchemy", q("Fullmetal Alchemist Brotherhood")),
    ("Hunter x Hunter", "Boy searching for his father", q("Hunter x Hunter 2011")),
    ("Mob Psycho 100", "Psychic middle schooler", q("Mob Psycho 100")),
    ("Bleach", "Soul Reaper fighting evil spirits", q("Bleach Thousand-Year Blood War")),
    ("Dragon Ball Z", "Legendary action series", q("Dragon Ball Z")),
    ("One Piece", "Pirate adventure series", q("One Piece anime key visual")),
]

CHILD = [
    ("Pokémon", "Ash and Pikachu's journey", q("Pokemon anime")),
    ("Digimon Adventure", "Digital world adventures", q("Digimon Adventure 1999 poster")),
    ("Doraemon", "Robotic cat from the future", q("Doraemon anime poster")),
    ("Yo-kai Watch", "Supernatural beings adventures", q("Yo-kai Watch anime poster")),
    ("Beyblade", "Spinning top battles", q("Beyblade anime poster")),
    ("Crayon Shin-chan", "Mischievous kindergarten boy", q("Crayon Shin-chan anime poster")),
    ("Astro Boy", "Powerful robot boy", q("Astro Boy Tezuka anime poster")),
]

FAMILY = [
    ("My Neighbor Totoro", "Magical forest spirits", q("My Neighbor Totoro Studio Ghibli poster")),
    ("Spirited Away", "Magical bathhouse adventure", q("Spirited Away Studio Ghibli poster")),
    ("Howl's Moving Castle", "Cursed woman and wizard", q("Howl's Moving Castle poster")),
    ("Kiki's Delivery Service", "Young witch's independence", q("Kiki's Delivery Service poster")),
    ("Princess Mononoke", "Forest gods vs humans", q("Princess Mononoke poster")),
    ("Castle in the Sky", "Legendary floating castle", q("Castle in the Sky Laputa poster")),
    ("Ponyo", "Magical fish girl", q("Ponyo poster")),
    ("The Secret World of Arrietty", "Tiny people beneath floorboards", q("Arrietty poster")),
]

# ---------- Helpers ----------
def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "image"

def pick_image(results):
    """
    Choose the best image from DuckDuckGo results:
    - prefer jpg/png
    - prefer vertical-ish, >= MIN_W x MIN_H if available
    """
    def score(r):
        w = r.get("width") or 0
        h = r.get("height") or 0
        ext_ok = str(r.get("image","")).lower().endswith((".jpg",".jpeg",".png"))
        # Prefer portrait, enough size, and proper ext
        portrait_bias = 1.3 if (h > w) else 1.0
        size_score = min(w/float(MIN_W), 2.0) + min(h/float(MIN_H), 2.0)
        return (1 if ext_ok else 0) * portrait_bias * size_score

    results_sorted = sorted(results, key=score, reverse=True)
    return results_sorted[0] if results_sorted else None

def fetch_first_good(query: str):
    # DuckDuckGo image search (no API key)
    with DDGS() as ddgs:
        results = list(ddgs.images(
            keywords=query,
            region="wt-wt",
            safesearch="moderate",
            size=None,       # any
            type_image=None, # any
            layout=None,     # any
            max_results=50
        ))
    return pick_image(results)

def download_image(url: str, dest_path: pathlib.Path):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # ensure extension
        ext = ".jpg"
        if url.lower().endswith(".png"):
            ext = ".png"
        p = dest_path.with_suffix(ext)
        p.write_bytes(r.content)
        return p
    except Exception as e:
        print(f"  ! download failed: {url} -> {e}")
        return None

def center_crop_resize(src: pathlib.Path, out_path: pathlib.Path, target_w=1920, target_h=800):
    with Image.open(src) as im:
        im = im.convert("RGB")
        # crop to target aspect ratio
        target_ratio = target_w / target_h
        w, h = im.size
        cur_ratio = w / float(h)
        if cur_ratio > target_ratio:
            # too wide -> crop left/right
            new_w = int(h * target_ratio)
            x0 = (w - new_w)//2
            box = (x0, 0, x0 + new_w, h)
        else:
            # too tall -> crop top/bottom
            new_h = int(w / target_ratio)
            y0 = (h - new_h)//2
            box = (0, y0, w, y0 + new_h)
        im = im.crop(box)
        im = im.resize((target_w, target_h), Image.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path, quality=92)

def process_section(pairs, out_dir):
    items = []
    for title, desc, query in pairs:
        print(f"\n→ {title}")
        result = fetch_first_good(query)
        if not result:
            print("  ! no result")
            continue
        url = result["image"]
        w, h = result.get("width"), result.get("height")
        print(f"  url: {url}")
        print(f"  size: {w}x{h}")
        base = slugify(title)
        dest = out_dir / f"{base}"
        saved = download_image(url, dest)
        if saved and MAKE_SLIDER_CROPS:
            crop_path = out_dir / f"{base}.slider.jpg"
            center_crop_resize(saved, crop_path, 1920, 800)
        if saved:
            rel = saved.relative_to(IMG_DIR).as_posix()
            items.append({
                "title": title,
                "description": desc,
                "src": f"img/{rel}",
                "alt": f"{title} – {desc}"
            })
    return items

def write_manifest(action_items, child_items, family_items):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "movies": {
            "action": action_items,
            "child": child_items,
            "family": family_items
        },
        "generated_at": int(time.time())
    }
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n🧭 Manifest written: {MANIFEST_PATH}")

def zip_everything():
    print(f"\n📦 Creating ZIP: {ZIP_PATH.name}")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in (OUT_ACTION, OUT_CHILD, OUT_FAMILY, MANIFEST_PATH):
            if p.is_file():
                z.write(p, p.relative_to(ROOT))
            else:
                for f in p.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(ROOT))
    print(f"Done: {ZIP_PATH}")

# ---------- Run ----------
if __name__ == "__main__":
    # Ensure folders
    for d in (OUT_ACTION, OUT_CHILD, OUT_FAMILY, MANIFEST_DIR):
        d.mkdir(parents=True, exist_ok=True)

    action_items = process_section(ACTION, OUT_ACTION)
    child_items  = process_section(CHILD,  OUT_CHILD)
    family_items = process_section(FAMILY, OUT_FAMILY)

    write_manifest(action_items, child_items, family_items)

    if MAKE_ZIP:
        zip_everything()

    print("\n✅ Finished.")
