import csv
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

SOURCE = "https://www.nord.com/en/services/documentation/manuals/manuals.jsp"
OUT = Path("manuals")
OUT.mkdir(exist_ok=True)
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; NordManualArchive/1.0)"})
pattern = re.compile(r"\bBU[\s_-]?(\d{4})\b", re.I)
queue = [SOURCE]
seen = set()
candidates = []
# Conservative crawler: official documentation page and directly linked PDF documents only.
while queue and len(seen) < 15:
    url = queue.pop(0)
    if url in seen:
        continue
    seen.add(url)
    try:
        response = session.get(url, timeout=35)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Page unavailable: {url}: {exc}")
        continue
    soup = BeautifulSoup(response.text, "html.parser")
    for a in soup.select("a[href]"):
        link = urljoin(response.url, a["href"])
        if urlparse(link).hostname not in ("www.nord.com", "nord.com"):
            continue
        label = a.get_text(" ", strip=True)
        if pattern.search(link + " " + label) and (".pdf" in link.lower() or "/cms/" in link.lower()):
            candidates.append((link, label))
        elif "manual" in link.lower() and link.lower().endswith((".jsp", ".html")) and link not in seen and link not in queue:
            queue.append(link)
print(f"Found {len(candidates)} candidate links on {len(seen)} pages")
records = []
done = set()
for url, label in candidates:
    m = pattern.search(url + " " + label)
    if not m:
        continue
    code = m.group(1)
    # Prefer English documents and avoid known non-English variants.
    lang = re.search(r"(?:[_/-])(en-us|en-gb|en|de|fr|it|es)(?:[_./-]|$)", url, re.I)
    language = lang.group(1).lower() if lang else "unverified"
    if language in ("de", "fr", "it", "es"):
        continue
    title = re.sub(r"\bBU[\s_-]?\d{4}\b", "", label, flags=re.I).strip(" -–_:")
    if not title:
        title = "Manual"
    title = re.sub(r'[\\/:*?"<>|]', "-", title)[:120]
    key = (code, language)
    if key in done:
        continue
    try:
        r = session.get(url, timeout=90)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF-"):
            print("Not a PDF:", url)
            continue
    except requests.RequestException as exc:
        print("Download failed:", url, exc)
        continue
    filename = f"BU {code} - {title}.pdf"
    path = OUT / filename
    if path.exists():
        path = OUT / f"BU {code} - {title} ({language}).pdf"
    path.write_bytes(r.content)
    done.add(key)
    records.append([code, title, language, url, str(path), len(r.content)])
    print("Saved", path)
    time.sleep(0.2)
with open("manifest.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["BU number", "Title", "Language", "Source URL", "File", "Bytes"])
    writer.writerows(records)
print(f"Downloaded {len(records)} verified PDFs")
if not records:
    raise SystemExit("No PDFs discovered; the catalogue may require JavaScript or a different download API. No archive files fabricated.")
