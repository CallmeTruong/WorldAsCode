import hashlib
from io import BytesIO
import json
import re
import urllib.request
import urllib.parse
import urllib.error
import time
from PIL import Image
from .config import ROOT
from .provider import write_json

SAMPLES = [("rietveld", "Rietveld Schröder House"), ("bauhaus", "Bauhaus Dessau"), ("fallingwater", "Fallingwater")]


def download_samples():
    dest = ROOT / "data"
    dest.mkdir(exist_ok=True)
    manifest = []
    def get(url, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        request=urllib.request.Request(url,headers={"User-Agent":"BuildingWorkflowResearch/0.1"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request,timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in (429,500,502,503) or attempt==2:
                    raise
                time.sleep(2+attempt*3)
    existing = {s["id"]: s for s in json.loads((dest / "samples.json").read_text(encoding="utf-8"))} if (dest / "samples.json").exists() else {}
    for sample_id, title in SAMPLES:
        path = dest / (sample_id + ".jpg")
        if sample_id in existing and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == existing[sample_id]["sha256"]:
            manifest.append(existing[sample_id])
            continue
        if sample_id == "villa-savoye":
            # Wikipedia's lead image is local to enwiki; explicitly choose a
            # Commons reference with retrievable attribution instead.
            file = "Villa Savoye (8237925975).jpg"
            page = None
        else:
            response = get("https://en.wikipedia.org/w/api.php", params={"action": "query", "titles": title.replace(" ","_"),
                "prop": "pageimages", "format": "json", "pithumbsize": 1200})
            page = next(iter(json.loads(response)["query"]["pages"].values()))
            file = page["pageimage"]
        metadata = get("https://commons.wikimedia.org/w/api.php", params={"action": "query", "titles": "File:" + file,
            "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth":1200, "redirects":1, "format": "json"})
        info = next(iter(json.loads(metadata)["query"]["pages"].values()))["imageinfo"][0]
        url = (page["thumbnail"]["source"] if page else info.get("thumburl",info["url"])).split("?")[0]
        image = get(url)
        im = Image.open(BytesIO(image)).convert("RGB")
        im.thumbnail((1200, 1200))
        im.save(path, quality=94)
        meta = info.get("extmetadata", {})
        clean = lambda value: re.sub("<[^>]*>", "", value)
        manifest.append({"id": sample_id, "title": title, "image": str(path.relative_to(ROOT)), "split": "development-smoke",
            "source_page": info.get("descriptionurl"), "source_url": url,
            "author": clean(meta.get("Artist", {}).get("value", "unknown")),
            "license": meta.get("LicenseShortName", {}).get("value", "unknown"),
            "license_url": meta.get("LicenseUrl", {}).get("value"), "crop": "none",
            "attribution": clean(meta.get("Permission", {}).get("value", "")),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "metadata": "No measured dimensions supplied; target is the named building, not surrounding structures."})
        write_json(dest / "samples.json", manifest)
    write_json(dest / "samples.json", manifest)
    return manifest
