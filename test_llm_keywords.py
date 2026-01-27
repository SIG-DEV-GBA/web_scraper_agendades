#!/usr/bin/env python
"""Compare static vs LLM keyword generation for Madrid events."""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from groq import Groq

from src.config.settings import get_settings
from src.core.supabase_client import get_supabase_client
from assign_unsplash_images import generate_keywords, generate_keywords_llm_batch


async def main():
    db = get_supabase_client()
    settings = get_settings()

    # Get Madrid events (all 20, even those with images)
    MADRID_SOURCE = "e3b66a63-e24b-4563-8803-07b36bf84ceb"
    response = (
        db.client.table("events")
        .select("id, title, summary")
        .eq("source_id", MADRID_SOURCE)
        .limit(20)
        .execute()
    )
    events = response.data
    print(f"Madrid events: {len(events)}")

    # Get categories for each event
    event_cats = {}
    for e in events:
        cat_resp = (
            db.client.table("event_categories")
            .select("category_id, categories(slug)")
            .eq("event_id", e["id"])
            .execute()
        )
        slugs = [
            r["categories"]["slug"]
            for r in cat_resp.data
            if r.get("categories") and r["categories"].get("slug")
        ]
        event_cats[e["id"]] = slugs

    # Generate LLM keywords
    sep = "=" * 70
    print(f"\n{sep}")
    print("  LLM KEYWORD GENERATION")
    print(sep)

    groq_client = Groq(api_key=settings.groq_api_key)

    events_for_llm = [
        {
            "id": e["id"],
            "title": e["title"],
            "summary": (e.get("summary") or "")[:150],
            "category": (
                event_cats.get(e["id"], [""])[0]
                if event_cats.get(e["id"])
                else ""
            ),
        }
        for e in events
    ]

    llm_kws = generate_keywords_llm_batch(events_for_llm, groq_client)
    print(f"  LLM returned keywords for {len(llm_kws)}/{len(events)} events")

    # Show comparison
    print(f"\n{sep}")
    print("  SIDE-BY-SIDE COMPARISON")
    print(sep)

    improved_count = 0
    for i, e in enumerate(events):
        cats = event_cats.get(e["id"], [])
        primary_cat = cats[0] if cats else None
        static_kws = generate_keywords(e["title"], e.get("summary"), primary_cat)
        llm = llm_kws.get(e["id"], ["(no LLM)"])

        title_short = e["title"][:55]
        improved = static_kws != llm and llm != ["(no LLM)"]
        if improved:
            improved_count += 1
        marker = "  <-- IMPROVED" if improved else ""

        print(f"  {i+1:2}. {title_short}")
        print(f"      Static: {static_kws}")
        print(f"      LLM:    {llm}{marker}")
        print()

    print(sep)
    print(f"  IMPROVED: {improved_count}/{len(events)} events got better keywords")
    print(sep)


if __name__ == "__main__":
    asyncio.run(main())
