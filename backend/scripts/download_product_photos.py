"""Download the reviewed manufacturer URLs in resources/photos/sources.json.

Keeps originals unchanged. Requires Pillow for image validation. Does not change
the database or publish images; consult each source's rights status before use.
Run from the repository root: python3 backend/scripts/download_product_photos.py
"""

import ast
import csv
import hashlib
import io
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "resources/photos"


def catalog():
    for file, key in (("seed.py", "PRODUCTS"), ("demo_data.py", "DEMO_PRODUCTS")):
        for node in ast.parse((ROOT / "backend/app" / file).read_text()).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == key for t in node.targets):
                yield from ast.literal_eval(node.value)


def download(job):
    source, index, url, previous = job
    name = source["name"]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    extracted = isinstance(index, str)
    relative = Path(index) if extracted else Path("products") / slug / f"{index:02}{suffix}"
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Image path must remain inside resources/photos")
    target = OUT / relative
    if not extracted and not target.exists():
        cached = sorted(target.parent.glob(f"{index:02}.*"))
        if cached:
            target = cached[0]
            relative = target.relative_to(OUT)
    row = {"product": name, "file": relative.as_posix(), "source_page": source["page"],
           "source_url": url, "rights": source.get("rights", "unverified")}
    try:
        if target.exists() and (extracted or previous.get(relative.as_posix(), {}).get("source_url") == url):
            data = target.read_bytes()
        elif extracted:
            raise ValueError("Extracted image is missing; restore it from the source PDF")
        else:
            result = subprocess.run(
                ["curl", "-sS", "-L", "--fail", "--max-time", "25", "--max-filesize", "5242880", url],
                capture_output=True, check=True,
            )
            data = result.stdout
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("File exceeds 5 MiB")
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError(f"Unexpected format: {image.format}")
            width, height = image.size
            row.update(width=width, height=height, format=image.format)
            row["meets_minimum"] = width >= 800 and height >= 600
            row["is_4_3"] = width * 3 == height * 4
            correct_suffix = {"JPEG": ".jpeg", "PNG": ".png", "WEBP": ".webp"}[image.format]
        old_target = target
        if target.suffix.lower() not in ({".jpg", ".jpeg"} if correct_suffix == ".jpeg" else {correct_suffix}):
            relative = relative.with_suffix(correct_suffix)
            target = OUT / relative
            row["file"] = relative.as_posix()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if old_target != target and old_target.exists():
            old_target.unlink()
        row.update(status="downloaded", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except UnidentifiedImageError:
        row.update(status="failed", error="Server returned content that is not a supported raster image")
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        row.update(status="failed", error=str(exc))
    return row


def main():
    sources = json.loads((OUT / "sources.json").read_text())
    names = {product[2] for product in catalog()}
    if len({source["name"] for source in sources}) != len(sources):
        raise SystemExit("Duplicate source product")
    if any(source["name"] not in names for source in sources):
        raise SystemExit("Source does not match the catalog")
    previous_file = OUT / "downloads.json"
    previous = {r["file"]: r for r in json.loads(previous_file.read_text())} if previous_file.exists() else {}
    jobs = [(source, i, url, previous) for source in sources for i, url in enumerate(source["urls"], 1)]
    jobs += [(source, relative, source["page"], previous)
             for source in sources for relative in source.get("extracted_files", [])]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(download, jobs))
    (OUT / "downloads.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "coverage.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["category", "product", "downloaded", "min_800x600", "exact_4_3", "status", "note", "source_page"])
        for category, _, name, *_ in catalog():
            photos = [r for r in results if r["product"] == name and r["status"] == "downloaded"]
            source = next((s for s in sources if s["name"] == name), {})
            writer.writerow([category, name, len(photos), sum(r["meets_minimum"] for r in photos),
                             sum(r["is_4_3"] for r in photos), "review_rights_and_framing" if photos else "missing",
                             source.get("note", ""), source.get("page", "")])
    print(f"Downloaded: {sum(r['status'] == 'downloaded' for r in results)}/{len(results)}; "
          f"products: {len({r['product'] for r in results if r['status'] == 'downloaded'})}/{len(names)}")


if __name__ == "__main__":
    main()
