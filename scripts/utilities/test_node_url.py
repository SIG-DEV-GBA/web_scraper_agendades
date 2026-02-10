#!/usr/bin/env python3
"""Test scraping Drupal node URL directly."""
import sys
import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FIRECRAWL_URL = "https://firecrawl.si-erp.cloud/scrape"

# Try node URL instead of friendly URL
node_url = "https://lagenda.org/node/40311"

print(f"Probando URL de nodo: {node_url}")
print("=" * 70)

resp = requests.post(FIRECRAWL_URL, json={"url": node_url, "waitFor": 3000}, timeout=90)
data = resp.json()
html = data.get("content", "")

soup = BeautifulSoup(html, "html.parser")

title = soup.find("title")
print(f"Title: {title.get_text() if title else 'N/A'}")

# Look for event content
h1 = soup.find("h1")
print(f"H1: {h1.get_text(strip=True) if h1 else 'N/A'}")

# Try to find body content in different ways
for selector in [".field-name-body", ".node-content", "article .content", ".field--name-body"]:
    elem = soup.select_one(selector)
    if elem:
        print(f"\n{selector}:")
        print(elem.get_text(strip=True)[:300])
        break

# Also try direct request (no Firecrawl)
print("\n" + "=" * 70)
print("Probando request directo (sin Firecrawl)...")
print("=" * 70)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get(node_url, headers=headers, timeout=30)
soup2 = BeautifulSoup(r.text, "html.parser")

title2 = soup2.find("title")
print(f"Title: {title2.get_text() if title2 else 'N/A'}")

h1_2 = soup2.find("h1")
print(f"H1: {h1_2.get_text(strip=True) if h1_2 else 'N/A'}")

# Check for meta description
meta_desc = soup2.find("meta", {"name": "description"})
if meta_desc:
    print(f"Meta description: {meta_desc.get('content', '')[:200]}")

# Look for Open Graph tags (often have event info)
og_tags = soup2.find_all("meta", property=lambda x: x and x.startswith("og:"))
if og_tags:
    print("\nOpen Graph tags:")
    for tag in og_tags:
        print(f"  {tag.get('property')}: {tag.get('content', '')[:100]}")
