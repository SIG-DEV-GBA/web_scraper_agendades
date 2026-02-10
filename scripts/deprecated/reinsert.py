"""Delete and reinsert Navarra events."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from supabase import create_client
from src.config import get_settings

settings = get_settings()
client = create_client(settings.supabase_url, settings.supabase_service_role_key)

events = client.table("events").select("id").like("external_id", "navarra_cultura_%").execute()
print(f"Deleting {len(events.data)} events...")

for event in events.data:
    eid = event["id"]
    client.table("event_locations").delete().eq("event_id", eid).execute()
    client.table("event_calendars").delete().eq("event_id", eid).execute()
    client.table("event_categories").delete().eq("event_id", eid).execute()
    client.table("event_organizers").delete().eq("event_id", eid).execute()
    client.table("event_registration").delete().eq("event_id", eid).execute()
    client.table("event_accessibility").delete().eq("event_id", eid).execute()
    client.table("event_contact").delete().eq("event_id", eid).execute()

client.table("events").delete().like("external_id", "navarra_cultura_%").execute()
print("Done")
