#!/usr/bin/env python3
"""Insert events from Teruel using RSS + Firecrawl + LLM extraction.

Flow:
1. Fetch RSS feed for event URLs
2. Use Firecrawl to scrape each detail page
3. Extract JSON-LD schema.org data (if available) or use LLM
4. Insert into Supabase with LLM enrichment

Usage:
    python insert_teruel_events.py
    python insert_teruel_events.py --limit 10
    python insert_teruel_events.py --dry-run
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, time

import feedparser
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LLM_ENABLED"] = "true"

# Fix encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.event_model import EventBatch, EventCreate, LocationType
from src.core.image_provider import get_image_provider
from src.core.llm_enricher import SourceTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Config
FIRECRAWL_URL = "https://firecrawl.si-erp.cloud/scrape"
RSS_URL = "https://www.teruel.es/eventos/feed/"
SOURCE_ID = "teruel_ayuntamiento"
SOURCE_NAME = "Agenda Cultural Ayuntamiento de Teruel"
CCAA = "Aragón"
PROVINCE = "Teruel"

# Colors for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def fetch_rss_urls() -> list[dict]:
    """Fetch event URLs from RSS feed."""
    print(f"  Fetching RSS from {RSS_URL}...")
    feed = feedparser.parse(RSS_URL)

    events = []
    for entry in feed.entries:
        events.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "pub_date": entry.get("published", ""),
        })

    print(f"  Found {len(events)} events in RSS")
    return events


def scrape_detail_page(url: str) -> dict | None:
    """Scrape event detail page using Firecrawl with Playwright."""
    from bs4 import BeautifulSoup

    try:
        response = requests.post(
            FIRECRAWL_URL,
            json={"url": url},
            timeout=90,
        )

        if response.status_code == 200:
            data = response.json()
            html = data.get("content", "")
            soup = BeautifulSoup(html, "html.parser")

            # Extract main content text for LLM
            main = soup.select_one("main, article, .content, .entry-content")
            text_content = main.get_text(separator=" ", strip=True)[:3000] if main else ""

            # Extract image from JSON-LD or og:image
            image_url = None
            # Try JSON-LD thumbnailUrl
            match = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', html)
            if match:
                image_url = match.group(1)
            # Fallback to og:image
            if not image_url:
                og_image = soup.find("meta", {"property": "og:image"})
                if og_image:
                    image_url = og_image.get("content")

            # Try to extract title from h1
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ""

            return {
                "html": html,
                "text_content": text_content,
                "title": title,
                "image_url": image_url,
            }
        else:
            logger.warning("firecrawl_error", url=url, status=response.status_code)
            return None

    except Exception as e:
        logger.error("firecrawl_exception", url=url, error=str(e))
        return None


def extract_json_ld(html: str) -> dict | None:
    """Extract JSON-LD Event schema from HTML."""
    if not html:
        return None

    # Find JSON-LD script tag
    match = re.search(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        # Handle @graph structure
        if isinstance(data, dict) and "@graph" in data:
            for item in data["@graph"]:
                if item.get("@type") == "Event":
                    return item
        elif isinstance(data, dict) and data.get("@type") == "Event":
            return data
        elif isinstance(data, list):
            for item in data:
                if item.get("@type") == "Event":
                    return item
    except json.JSONDecodeError:
        pass

    return None


def parse_date(date_str: str) -> date | None:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        # Handle ISO format: 2026-02-06T19:30:00+01:00
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.date()
    except ValueError:
        return None


def parse_time(date_str: str) -> time | None:
    """Parse ISO date string to time object."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.hour > 0 or dt.minute > 0:
            return dt.time()
    except ValueError:
        pass
    return None


def extract_event_from_json_ld(json_ld: dict, url: str) -> dict:
    """Extract event data from JSON-LD schema."""
    event = {
        "title": json_ld.get("name", ""),
        "description": json_ld.get("description", ""),
        "external_url": url,
        "external_id": f"{SOURCE_ID}_{url.rstrip('/').split('/')[-1]}",
    }

    # Dates
    start_date_str = json_ld.get("startDate", "")
    end_date_str = json_ld.get("endDate", "")
    event["start_date"] = parse_date(start_date_str)
    event["end_date"] = parse_date(end_date_str)
    event["start_time"] = parse_time(start_date_str)

    # Location
    location = json_ld.get("location", {})
    if isinstance(location, dict):
        event["venue_name"] = location.get("name", "")
        address = location.get("address", {})
        if isinstance(address, dict):
            event["city"] = address.get("addressLocality", "Teruel")
            event["address"] = address.get("streetAddress", "")
        elif isinstance(address, str):
            event["address"] = address

    # Image
    images = json_ld.get("image", [])
    if isinstance(images, list) and images:
        event["image_url"] = images[0]
    elif isinstance(images, str):
        event["image_url"] = images

    # Price/Free
    offers = json_ld.get("offers", {})
    if isinstance(offers, dict):
        price = offers.get("price", 0)
        if price == 0 or price == "0":
            event["is_free"] = True
        else:
            event["is_free"] = False
            try:
                event["price"] = float(price)
            except (ValueError, TypeError):
                pass

    # Organizer
    organizer = json_ld.get("organizer", {})
    if isinstance(organizer, dict):
        event["organizer_name"] = organizer.get("name", "")

    # Event status
    status = json_ld.get("eventStatus", "")
    if "Cancelled" in status:
        event["is_cancelled"] = True

    return event


def extract_event_from_markdown(markdown: str, url: str, title: str) -> dict:
    """Fallback: extract basic event data from markdown using regex."""
    event = {
        "title": title,
        "description": markdown[:1000] if markdown else "",
        "external_url": url,
        "external_id": f"{SOURCE_ID}_{url.rstrip('/').split('/')[-1]}",
        "start_date": date.today(),  # Will be enriched by LLM
    }

    # Try to extract dates from markdown
    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", markdown)
    if date_match:
        try:
            d, m, y = date_match.groups()
            event["start_date"] = date(int(y), int(m), int(d))
        except ValueError:
            pass

    # Try to extract price
    if any(kw in markdown.lower() for kw in ["gratuito", "gratis", "entrada libre", "free"]):
        event["is_free"] = True

    return event


async def process_events(
    limit: int = 20,
    dry_run: bool = False,
    upsert: bool = False,
) -> dict:
    """Process Teruel events: RSS -> Firecrawl -> Insert."""
    print(f"\n{'='*60}")
    print(f"{BOLD}TERUEL_AYUNTAMIENTO{RESET}")
    print(f"{'='*60}")
    print(f"  CCAA: {CCAA}")
    print(f"  Method: RSS + Firecrawl + JSON-LD/LLM")

    # 1. Fetch RSS
    rss_events = fetch_rss_urls()
    if not rss_events:
        return {"source": SOURCE_ID, "error": "No events in RSS"}

    # 2. Scrape each detail page
    print(f"\n  Scraping {min(limit, len(rss_events))} detail pages with Firecrawl...")
    events = []

    for i, rss_event in enumerate(rss_events[:limit]):
        url = rss_event["url"]
        title = rss_event["title"]

        print(f"    [{i+1}/{min(limit, len(rss_events))}] {title[:40]}...", end=" ")

        page_data = scrape_detail_page(url)

        if page_data:
            # Extract basic event data from scraped content
            event = {
                "title": page_data.get("title") or title,
                "description": "",  # Will be filled by LLM
                "external_url": url,
                "external_id": f"{SOURCE_ID}_{url.rstrip('/').split('/')[-1]}",
                "image_url": page_data.get("image_url"),
                "text_content": page_data.get("text_content", "")[:2000],
            }

            # Try JSON-LD for structured data
            json_ld = extract_json_ld(page_data.get("html", ""))
            if json_ld:
                ld_data = extract_event_from_json_ld(json_ld, url)
                # Merge JSON-LD data
                for k, v in ld_data.items():
                    if v and not event.get(k):
                        event[k] = v
                print(f"{GREEN}JSON-LD{RESET}")
            else:
                print(f"{YELLOW}HTML{RESET}")

            events.append(event)
        else:
            print(f"{RED}FAILED{RESET}")

    print(f"\n  Successfully scraped: {len(events)} events")

    if not events:
        return {"source": SOURCE_ID, "error": "No events scraped"}

    # Debug: show what dates we extracted
    print(f"\n  Date extraction debug:")
    for e in events[:3]:
        print(f"    {e['title'][:40]}: start_date={e.get('start_date')}")

    # 3. Filter future events
    today = date.today()
    future_events = []
    for e in events:
        start = e.get("start_date")
        if start:
            if isinstance(start, date) and start >= today:
                future_events.append(e)
            elif start is None:
                future_events.append(e)  # Include if no date (will use today)
        else:
            future_events.append(e)  # Include if no date

    print(f"  Future events: {len(future_events)}")
    events = future_events[:limit]

    if not events:
        return {"source": SOURCE_ID, "parsed": 0, "inserted": 0}

    # 4. Extract structured data with LLM
    print(f"\n  Extracting structured data with LLM...")
    enricher = get_llm_enricher()

    # First pass: extract structured data from text content
    for event in events:
        text = event.get("text_content", "")
        if text and not event.get("start_date"):
            # Parse dates from text like "12 enero 2026 / 08:00 - 11 febrero 2026 / 17:00"
            date_match = re.search(r"(\d{1,2})\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(\d{4})", text, re.IGNORECASE)
            if date_match:
                day, month_name, year = date_match.groups()
                months = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                         "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
                try:
                    event["start_date"] = date(int(year), months[month_name.lower()], int(day))
                except ValueError:
                    pass

            # Extract time like "08:00" or "19:30"
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            if time_match:
                try:
                    event["start_time"] = time(int(time_match.group(1)), int(time_match.group(2)))
                except ValueError:
                    pass

            # Check for free/gratis
            if any(kw in text.lower() for kw in ["gratuito", "gratis", "entrada libre", "free"]):
                event["is_free"] = True

            # Default city
            if not event.get("city"):
                event["city"] = "Teruel"

    # Second pass: standard LLM enrichment for categories, summary, etc.
    print(f"  Running category enrichment...")
    events_for_llm = []
    for e in events:
        events_for_llm.append({
            "id": e["external_id"],
            "title": e["title"],
            "description": e.get("text_content", "")[:800],
            "@type": "",
            "audience": "",
            "price_info": "",
            # Location fields for contextualized image_keywords
            "city": e.get("city") or "Teruel",
            "province": PROVINCE,
            "comunidad_autonoma": CCAA,
            "venue_name": e.get("venue_name", ""),
        })

    enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.BRONCE)
    print(f"  Enriched: {len(enrichments)} events")

    # 5. Create EventCreate objects
    event_creates = []
    for raw in events:
        enrichment = enrichments.get(raw["external_id"])

        # Determine is_free
        is_free = raw.get("is_free")
        price = raw.get("price")
        price_info = None

        if enrichment:
            if enrichment.price is not None:
                price = enrichment.price
                is_free = False
            if enrichment.is_free is not None and is_free is None:
                is_free = enrichment.is_free
            if enrichment.price_details:
                price_info = enrichment.price_details

        # Use text_content as description if no description
        description = raw.get("description") or raw.get("text_content", "")[:500]

        event = EventCreate(
            title=raw["title"],
            description=description,
            summary=enrichment.summary if enrichment else None,
            start_date=raw.get("start_date") or date.today(),
            end_date=raw.get("end_date"),
            start_time=raw.get("start_time"),
            location_type=LocationType.PHYSICAL,
            venue_name=raw.get("venue_name"),
            address=raw.get("address"),
            city=raw.get("city") or "Teruel",
            province=PROVINCE,
            comunidad_autonoma=CCAA,
            source_id=SOURCE_ID,
            external_url=raw["external_url"],
            external_id=raw["external_id"],
            source_image_url=raw.get("image_url"),
            category_slugs=enrichment.category_slugs if enrichment else [],
            is_free=is_free,
            price=price,
            price_info=price_info,
        )
        event_creates.append(event)

    # 6. Fetch images for events without source_image_url
    image_provider = get_image_provider()
    images_found = 0
    if image_provider.unsplash:
        print(f"  Fetching images for events without source image...")
        for event in event_creates:
            if not event.source_image_url:
                enrichment = enrichments.get(event.external_id)
                if enrichment and enrichment.image_keywords:
                    image_url = image_provider.get_image(
                        keywords=enrichment.image_keywords,
                        category=enrichment.category_slugs[0] if enrichment.category_slugs else "default",
                    )
                    if image_url:
                        event.source_image_url = image_url
                        images_found += 1
        print(f"  Images found: {images_found}")

    # Stats
    category_counts = {}
    for e in event_creates:
        cat = e.category_slugs[0] if e.category_slugs else "N/A"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    free_count = sum(1 for e in event_creates if e.is_free is True)
    paid_count = sum(1 for e in event_creates if e.is_free is False)
    with_image = sum(1 for e in event_creates if e.source_image_url)

    print(f"  Categories: {category_counts}")
    print(f"  Pricing: {free_count} GRATIS, {paid_count} PAGO")
    print(f"  With images: {with_image}/{len(event_creates)}")

    if dry_run:
        print(f"\n  {YELLOW}DRY RUN - Not inserting to database{RESET}")
        print(f"  Would insert {len(event_creates)} events")

        print(f"\n  {BOLD}Sample events:{RESET}")
        for i, e in enumerate(event_creates[:5]):
            cat = e.category_slugs[0] if e.category_slugs else "N/A"
            free = "GRATIS" if e.is_free else ("PAGO" if e.is_free is False else "?")
            has_img = "IMG" if e.source_image_url else "-"
            print(f"    {i+1}. [{cat}] [{free}] [{has_img}] {e.title[:45]}")
            print(f"       {e.city or '?'} | {e.start_date}")

        return {
            "source": SOURCE_ID,
            "ccaa": CCAA,
            "parsed": len(event_creates),
            "inserted": 0,
            "dry_run": True,
        }

    # 7. Insert to Supabase
    print(f"\n  {CYAN}Inserting to Supabase...{RESET}")
    client = get_supabase_client()

    batch = EventBatch(
        source_id=SOURCE_ID,
        source_name=SOURCE_NAME,
        ccaa=CCAA,
        scraped_at=datetime.now().isoformat(),
        events=event_creates,
        total_found=len(rss_events),
    )

    stats = await client.save_batch(batch, skip_existing=not upsert)

    print(f"  {GREEN}Inserted: {stats['inserted']}{RESET}")
    print(f"  Skipped (existing): {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")

    return {
        "source": SOURCE_ID,
        "ccaa": CCAA,
        "parsed": len(event_creates),
        "inserted": stats["inserted"],
        "skipped": stats["skipped"],
        "failed": stats["failed"],
    }


async def main():
    parser = argparse.ArgumentParser(description="Insert Teruel events using Firecrawl")
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Max events to process (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without inserting to database",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Update existing events instead of skipping them",
    )

    args = parser.parse_args()

    print(f"\n{'#'*60}")
    print(f"# TERUEL EVENTS INSERTION (Firecrawl + JSON-LD)")
    print(f"# Limit: {args.limit}, Dry run: {args.dry_run}, Upsert: {args.upsert}")
    print(f"{'#'*60}")

    try:
        result = await process_events(
            limit=args.limit,
            dry_run=args.dry_run,
            upsert=args.upsert,
        )

        print(f"\n{'#'*60}")
        print(f"# {BOLD}FINAL RESULT{RESET}")
        print(f"{'#'*60}")

        if "error" in result:
            print(f"\n{RED}ERROR: {result['error']}{RESET}")
        else:
            print(f"\n  Parsed: {result.get('parsed', 0)}")
            print(f"  Inserted: {result.get('inserted', 0)}")
            if result.get("dry_run"):
                print(f"\n{YELLOW}This was a dry run. Use without --dry-run to insert.{RESET}")

    except Exception as e:
        print(f"\n{RED}FATAL ERROR: {e}{RESET}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
