"""Generate HTML preview of events from a source adapter."""

import asyncio
import html
import sys

async def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "viveceuta"

    from src.adapters import get_adapter

    adapter_cls = get_adapter(slug)
    if not adapter_cls:
        print(f"Adapter '{slug}' not found")
        return

    adapter = adapter_cls()

    # Fetch raw events
    raw_events = await adapter.fetch_events(enrich=False, fetch_details=False, limit=50)

    # Parse into EventCreate
    parsed = []
    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            parsed.append(event)

    # Generate HTML
    cards_html = ""
    for i, ev in enumerate(parsed, 1):
        img = ev.source_image_url or "https://via.placeholder.com/400x200?text=Sin+imagen"
        title = html.escape(ev.title or "Sin título")
        date_str = ev.start_date.strftime("%d/%m/%Y") if ev.start_date else "?"
        time_str = ""
        if ev.start_time:
            time_str = ev.start_time.strftime("%H:%M")
            if ev.end_time:
                time_str += f" - {ev.end_time.strftime('%H:%M')}"

        venue = html.escape(ev.venue_name or "")
        address = html.escape(ev.address or "")
        city = html.escape(ev.city or "")
        province = html.escape(ev.province or "")
        ccaa = html.escape(ev.comunidad_autonoma or "")
        desc = html.escape((ev.description or "")[:300])
        ext_url = ev.external_url or "#"
        ext_id = html.escape(ev.external_id or "?")
        if ev.is_free:
            price_badge = '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">GRATIS</span>'
        elif ev.price:
            price_badge = f'<span style="background:#6366f1;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">{ev.price:.0f} EUR</span>'
        elif ev.price_info:
            price_badge = f'<span style="background:#eab308;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">{html.escape(ev.price_info)}</span>'
        else:
            price_badge = '<span style="background:#9ca3af;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">Sin precio</span>'

        organizer_html = ""
        if ev.organizer and ev.organizer.name:
            organizer_html = f'<div style="font-size:12px;color:#6b7280;margin-top:4px;">Organiza: {html.escape(ev.organizer.name)}</div>'

        cards_html += f'''
        <div style="border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
            <img src="{img}" style="width:100%;height:180px;object-fit:cover;" onerror="this.src='https://via.placeholder.com/400x200?text=Sin+imagen'"/>
            <div style="padding:16px;">
                <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                    <h3 style="margin:0;font-size:16px;color:#111827;flex:1;">{title}</h3>
                    {price_badge}
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                    <span style="font-size:13px;color:#6366f1;">📅 {date_str}</span>
                    {"<span style='font-size:13px;color:#6366f1;'>🕐 " + time_str + "</span>" if time_str else ""}
                </div>
                {"<div style='font-size:13px;color:#374151;margin-bottom:4px;'>📍 " + venue + "</div>" if venue else ""}
                {"<div style='font-size:12px;color:#6b7280;margin-bottom:4px;'>" + address + "</div>" if address else ""}
                <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">{city}{", " + province if province and province != city else ""} — {ccaa}</div>
                {organizer_html}
                <p style="font-size:13px;color:#4b5563;margin:8px 0;line-height:1.4;">{desc}{"..." if len(ev.description or "") > 300 else ""}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:12px;border-top:1px solid #f3f4f6;">
                    <code style="font-size:11px;color:#9ca3af;">{ext_id}</code>
                    <a href="{ext_url}" target="_blank" style="font-size:13px;color:#6366f1;text-decoration:none;">Ver detalle →</a>
                </div>
            </div>
        </div>'''

    page_html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Preview: {html.escape(slug)} — {len(parsed)} eventos</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; padding: 20px; }}
    </style>
</head>
<body>
    <div style="max-width:1200px;margin:0 auto;">
        <div style="text-align:center;margin-bottom:24px;">
            <h1 style="font-size:24px;color:#111827;">🔍 Preview: <code>{html.escape(slug)}</code></h1>
            <p style="color:#6b7280;margin-top:4px;">{len(raw_events)} raw → {len(parsed)} válidos — Así llegarían a AgendaDES</p>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px;">
            {cards_html}
        </div>
    </div>
</body>
</html>'''

    out_file = f"_preview_{slug}.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(page_html)

    print(f"OK: {len(parsed)} eventos -> {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
