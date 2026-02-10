#!/usr/bin/env python
"""Assign Unsplash images to events based on title and category.

Uses the ImageProvider system (with cache/dedup) to search Unsplash
and assign unique images to events that don't have one yet.

Usage:
    python assign_unsplash_images.py                    # All events without images
    python assign_unsplash_images.py --source madrid    # Only Madrid events
    python assign_unsplash_images.py --dry-run          # Preview without updating DB
    python assign_unsplash_images.py --all-sources      # Process all sources
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time as time_mod

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from groq import Groq

from src.config.settings import get_settings
from src.core.image_provider import ImageProvider, ImageResult, get_image_provider
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Madrid source UUID
MADRID_SOURCE_ID = "e3b66a63-e24b-4563-8803-07b36bf84ceb"

# Source slug -> UUID mapping
SOURCE_IDS = {
    "madrid": MADRID_SOURCE_ID,
    "euskadi": "93abddb9-09c9-4c2f-9c5f-4ac7a2db0626",
    "castilla_leon": "30592765-8d44-43cd-bbb9-cc1cf1b2823b",
    "andalucia": "1fcc139a-6c30-4c12-b72d-a64a9a1f8126",
    "catalunya": "761d9475-dc35-4b50-8682-97f7300272a1",
}

# ── Keyword generation from Spanish titles ──────────────────────────

# Spanish term -> English Unsplash keywords
TERM_MAP = {
    # Music
    "concierto": ["concert", "music", "live"],
    "orkestra": ["orchestra", "classical", "concert hall"],
    "orquesta": ["orchestra", "classical", "concert hall"],
    "opera": ["opera", "theater", "performance"],
    "ópera": ["opera", "theater", "performance"],
    "coro": ["choir", "singing", "concert"],
    "jazz": ["jazz", "music", "concert"],
    "flamenco": ["flamenco", "dance", "spain"],
    "rock": ["rock", "concert", "live music"],
    "folk": ["folk music", "acoustic", "concert"],
    "música": ["music", "concert", "performance"],
    "musica": ["music", "concert", "performance"],
    # Theater / Dance
    "teatro": ["theater", "stage", "performance"],
    "danza": ["dance", "ballet", "performance"],
    "ballet": ["ballet", "dance", "performance"],
    "circo": ["circus", "acrobat", "show"],
    "magia": ["magic", "show", "illusion"],
    "títeres": ["puppets", "children", "theater"],
    "marionetas": ["puppets", "theater", "show"],
    # Visual arts
    "exposición": ["exhibition", "art gallery", "museum"],
    "exposicion": ["exhibition", "art gallery", "museum"],
    "fotografía": ["photography", "gallery", "exhibition"],
    "fotografia": ["photography", "gallery", "exhibition"],
    "pintura": ["painting", "art", "gallery"],
    "escultura": ["sculpture", "art", "museum"],
    "museo": ["museum", "art", "exhibition"],
    "galería": ["gallery", "art", "exhibition"],
    # Film
    "cine": ["cinema", "film", "movie"],
    "película": ["film", "cinema", "movie"],
    "documental": ["documentary", "film", "screening"],
    # Literature / Education
    "libro": ["books", "reading", "library"],
    "lectura": ["reading", "books", "library"],
    "biblioteca": ["library", "books", "reading"],
    "conferencia": ["conference", "talk", "seminar"],
    "taller": ["workshop", "learning", "classroom"],
    "curso": ["course", "education", "workshop"],
    "charla": ["talk", "lecture", "seminar"],
    "coloquio": ["debate", "discussion", "seminar"],
    "presentación": ["presentation", "book", "event"],
    # Festivals / Celebration
    "festival": ["festival", "celebration", "event"],
    "feria": ["fair", "market", "festival"],
    "fiesta": ["celebration", "party", "festival"],
    "carnaval": ["carnival", "costume", "celebration"],
    "navidad": ["christmas", "holiday", "celebration"],
    # Sports / Outdoor
    "deporte": ["sports", "fitness", "outdoor"],
    "deportiva": ["sports", "athletic", "competition"],
    "senderismo": ["hiking", "nature", "trail"],
    "ruta": ["tour", "walk", "sightseeing"],
    "visita": ["tour", "visit", "guided"],
    "excursión": ["excursion", "nature", "outdoor"],
    # Technology
    "tecnología": ["technology", "digital", "innovation"],
    "hackathon": ["hackathon", "coding", "technology"],
    "digital": ["digital", "technology", "innovation"],
    # Community
    "infantil": ["children", "kids", "family"],
    "familiar": ["family", "children", "community"],
    "niños": ["children", "kids", "playground"],
    "jornada": ["conference", "event", "seminar"],
    "encuentro": ["meeting", "gathering", "community"],
    "mercado": ["market", "shopping", "street"],
    "gastro": ["food", "gastronomy", "cuisine"],
}

# Category -> fallback keywords
CATEGORY_KEYWORDS = {
    "cultural": ["culture", "art", "event"],
    "social": ["community", "people", "gathering"],
    "economica": ["business", "economy", "conference"],
    "politica": ["politics", "government", "debate"],
    "sanitaria": ["health", "wellness", "medicine"],
    "tecnologia": ["technology", "digital", "innovation"],
}


def generate_keywords(
    title: str,
    summary: str | None = None,
    category: str | None = None,
) -> list[str]:
    """Generate English search keywords from a Spanish event title + summary.

    Static fallback when LLM is not available.
    """
    search_text = f"{title} {summary or ''}".lower()
    keywords = []

    matches = []
    for term, kws in TERM_MAP.items():
        if term in search_text:
            matches.append((len(term), kws))

    if matches:
        matches.sort(key=lambda x: -x[0])
        keywords.extend(matches[0][1])
    elif category:
        cat_kws = CATEGORY_KEYWORDS.get(category, [])
        keywords.extend(cat_kws)

    if not keywords:
        keywords = ["event", "culture", "spain"]

    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:3]


# ── LLM-based keyword generation ────────────────────────────

IMAGE_KEYWORDS_PROMPT = """You generate Unsplash search keywords for Spanish cultural events.

For each event, output exactly 3 English keywords that would find the BEST stock photo
to represent this SPECIFIC event. Be contextually precise:

- "Concierto infantil" → "children music classroom" (NOT "rock concert stage")
- "Exposición de fotografía" → "photography gallery exhibition" (NOT "painting museum")
- "Taller de robótica para niños" → "kids robotics workshop" (NOT "industrial robot")
- "Ópera Werther" → "opera theater stage" (NOT "rock concert")
- "Ruta senderismo montaña" → "mountain hiking trail" (NOT "city walking tour")
- "Club de lectura inglés" → "book club reading group" (NOT "english classroom")

Think about the TARGET AUDIENCE (children vs adults), the VENUE TYPE (theater vs outdoor vs library),
and the SPECIFIC ACTIVITY (not just the general category).

Input events (JSON array):
{events_json}

Output ONLY a JSON object mapping event id to array of 3 keywords:
{{"id1": ["kw1", "kw2", "kw3"], "id2": ["kw1", "kw2", "kw3"], ...}}"""


def generate_keywords_llm_batch(
    events: list[dict],
    groq_client: Groq,
    model: str = "llama-3.3-70b-versatile",
) -> dict[str, list[str]]:
    """Generate contextual image keywords for a batch of events using LLM.

    Args:
        events: List of dicts with 'id', 'title', 'summary', 'category' keys
        groq_client: Initialized Groq client
        model: Model to use (fast model, keywords don't need huge reasoning)

    Returns:
        Dict mapping event_id -> list of 3 English keywords
    """
    # Build compact event list for prompt
    events_for_prompt = []
    for e in events:
        events_for_prompt.append({
            "id": e["id"],
            "title": e["title"],
            "summary": (e.get("summary") or "")[:150],
            "category": e.get("category") or "",
        })

    prompt = IMAGE_KEYWORDS_PROMPT.format(
        events_json=json.dumps(events_for_prompt, ensure_ascii=False)
    )

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an image search expert. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        content = response.choices[0].message.content
        if not content:
            return {}

        # Parse JSON - handle markdown code blocks
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content)

        # Validate: each value should be a list of strings
        validated = {}
        for eid, kws in result.items():
            if isinstance(kws, list) and all(isinstance(k, str) for k in kws):
                validated[eid] = kws[:3]
        return validated

    except Exception as e:
        logger.error("llm_keywords_error", error=str(e)[:100])
        return {}


async def get_events_without_images(
    db,
    source_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query events without image_url from Supabase."""
    query = (
        db.client.table("events")
        .select("id, title, summary, source_id")
        .is_("image_url", "null")
        .order("created_at", desc=True)
        .limit(limit)
    )

    if source_id:
        query = query.eq("source_id", source_id)

    response = query.execute()
    return response.data


async def get_event_categories(db, event_id: str) -> list[str]:
    """Get category slugs for an event."""
    try:
        response = (
            db.client.table("event_categories")
            .select("category_id, categories(slug)")
            .eq("event_id", event_id)
            .execute()
        )
        slugs = []
        for row in response.data:
            cat = row.get("categories")
            if cat and cat.get("slug"):
                slugs.append(cat["slug"])
        return slugs
    except Exception:
        return []


async def update_event_image(db, event_id: str, image_url: str) -> bool:
    """Update event image_url in Supabase."""
    try:
        from datetime import datetime

        response = (
            db.client.table("events")
            .update({
                "image_url": image_url,
                "updated_at": datetime.now().isoformat(),
            })
            .eq("id", event_id)
            .execute()
        )
        return len(response.data) > 0
    except Exception as e:
        logger.error("update_image_error", event_id=event_id, error=str(e))
        return False


async def main():
    parser = argparse.ArgumentParser(description="Assign Unsplash images to events")
    parser.add_argument(
        "--source", "-s",
        choices=list(SOURCE_IDS.keys()),
        default=None,
        help="Filter by source (default: all events without images)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="Max events to process (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview keywords and images without updating DB",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between Unsplash API calls in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    # Resolve source_id
    source_id = SOURCE_IDS.get(args.source) if args.source else None
    source_label = args.source or "all"

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  UNSPLASH IMAGE ASSIGNMENT")
    print(sep)
    print(f"  Source: {source_label}")
    print(f"  Limit: {args.limit}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Delay: {args.delay}s")

    # Init
    db = get_supabase_client()
    provider = get_image_provider()
    settings = get_settings()

    # Init Groq for LLM keywords
    groq_client = None
    if settings.groq_api_key:
        try:
            groq_client = Groq(api_key=settings.groq_api_key)
            print(f"  LLM keywords: enabled (Groq)")
        except Exception:
            print(f"  LLM keywords: disabled (Groq init failed)")
    else:
        print(f"  LLM keywords: disabled (no API key)")

    print(f"  Providers: {', '.join(provider.providers_available)}")
    print(f"  Cache size: {provider.cache_size}")
    print()

    # Get events
    events = await get_events_without_images(db, source_id, args.limit)
    print(f"  Events without images: {len(events)}")

    if not events:
        print("  Nothing to do!")
        return

    # Pre-fetch categories for all events
    event_cats: dict[str, list[str]] = {}
    for event in events:
        cats = await get_event_categories(db, event["id"])
        event_cats[event["id"]] = cats

    # Generate LLM keywords in batch (10 at a time)
    llm_keywords: dict[str, list[str]] = {}
    if groq_client:
        print(f"\n  Generating contextual keywords via LLM...")
        batch_size = 15
        for batch_start in range(0, len(events), batch_size):
            batch = events[batch_start:batch_start + batch_size]
            events_for_llm = [
                {
                    "id": e["id"],
                    "title": e["title"],
                    "summary": (e.get("summary") or "")[:150],
                    "category": event_cats.get(e["id"], [""])[0] if event_cats.get(e["id"]) else "",
                }
                for e in batch
            ]
            batch_result = generate_keywords_llm_batch(events_for_llm, groq_client)
            llm_keywords.update(batch_result)
            print(f"    Batch {batch_start // batch_size + 1}: {len(batch_result)}/{len(batch)} keywords generated")

        print(f"  LLM keywords total: {len(llm_keywords)}/{len(events)}")

    # Process each event
    updated = 0
    failed = 0
    skipped = 0

    print(f"\n{'-' * 60}")

    for i, event in enumerate(events):
        event_id = event["id"]
        title = event["title"]
        summary = event.get("summary") or ""

        # Get categories (already fetched)
        cats = event_cats.get(event_id, [])
        primary_cat = cats[0] if cats else None

        # Use LLM keywords if available, otherwise static fallback
        if event_id in llm_keywords:
            keywords = llm_keywords[event_id]
            kw_source = "LLM"
        else:
            keywords = generate_keywords(title, summary, primary_cat)
            kw_source = "static"

        # Display
        title_short = title[:50] + "..." if len(title) > 50 else title
        cat_str = ",".join(cats[:2]) if cats else "N/A"
        print(f"  {i+1:3}. {title_short}")
        print(f"       Cat: {cat_str} | Keywords [{kw_source}]: {keywords}")

        if args.dry_run:
            skipped += 1
            print(f"       [DRY RUN] Would search: {' '.join(keywords)}")
            print()
            continue

        # Search Unsplash
        result = provider.get_image_full(
            keywords=keywords,
            category=primary_cat or "default",
        )

        if result:
            # Update DB
            success = await update_event_image(db, event_id, result.url)
            if success:
                updated += 1
                author = result.author or "?"
                print(f"       -> {result.url[:60]}...")
                print(f"       Photo by {author} on {result.provider}")
            else:
                failed += 1
                print(f"       [ERROR] DB update failed")
        else:
            # Use fallback
            fallback_url = provider._get_fallback(primary_cat or "default")
            success = await update_event_image(db, event_id, fallback_url)
            if success:
                updated += 1
                print(f"       -> [FALLBACK] {fallback_url[:60]}...")
            else:
                failed += 1
                print(f"       [ERROR] Fallback update failed")

        print()

        # Rate limiting
        if i < len(events) - 1:
            time_mod.sleep(args.delay)

    # Summary
    print(f"{sep}")
    print(f"  RESULTS:")
    print(f"  Updated: {updated}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    print(f"  Cache:   {provider.cache_size} images cached")
    print(sep)


if __name__ == "__main__":
    asyncio.run(main())
