"""Pydantic models for events that map to Supabase schema."""

from datetime import date, time
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocationType(str, Enum):
    """Type of event location.

    Values must match Supabase modality enum: presencial, online, hibrido
    """

    PHYSICAL = "presencial"
    ONLINE = "online"
    HYBRID = "hibrido"


class EventSource(str, Enum):
    """Source of the event."""

    MANUAL = "manual"
    IMPORT = "import"
    API = "api"
    SCRAPER = "scraper"


class OrganizerType(str, Enum):
    """Type of event organizer.

    Values must match Supabase organizer_type enum:
    empresa, asociacion, institucion, otro
    """

    INSTITUCION = "institucion"  # gobierno, ayuntamiento, administración pública
    EMPRESA = "empresa"
    ASOCIACION = "asociacion"
    OTRO = "otro"


class EventOrganizer(BaseModel):
    """Organizer information for an event."""

    name: str
    type: OrganizerType = OrganizerType.OTRO
    url: str | None = None
    logo_url: str | None = None


class EventContact(BaseModel):
    """Contact information for an event (maps to event_contact table)."""

    name: str | None = None  # Contact person name
    email: str | None = None
    phone: str | None = None
    info: str | None = None  # Additional contact info (hours, etc.)


class EventAccessibility(BaseModel):
    """Accessibility information for an event (maps to event_accessibility table)."""

    wheelchair_accessible: bool = False
    sign_language: bool = False
    hearing_loop: bool = False
    braille_materials: bool = False
    other_facilities: str | None = None
    notes: str | None = None


class EventCreate(BaseModel):
    """Model for creating a new event (input from scrapers)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # Required fields
    title: Annotated[str, Field(min_length=1, max_length=500)]
    start_date: date

    # Optional basic fields
    description: str | None = None
    summary: str | None = None  # Short summary/excerpt
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool = False

    # Location - detailed
    location_type: LocationType = LocationType.PHYSICAL
    venue_name: str | None = None
    address: str | None = None  # Full street address
    district: str | None = None  # District/neighborhood
    city: str | None = None
    province: str | None = None
    comunidad_autonoma: str | None = None
    postal_code: str | None = None
    country: str = "España"
    latitude: float | None = None
    longitude: float | None = None
    location_details: str | None = None  # Additional info: parking, access, meeting point, etc.

    # Online event
    online_url: str | None = None

    # Categories (N:M - multiple categories per event)
    category_name: str | None = None  # From scraper (e.g., "teatro", "TeatroPerformance")
    category_slugs: list[str] = Field(default_factory=list)  # Resolved DB category slugs (e.g., ["cultural", "social"])
    category_id: UUID | None = None  # Legacy - not used

    # Organizer (stored in event_organizers table)
    organizer: EventOrganizer | None = None
    # Legacy fields for backward compatibility
    organizer_name: str | None = None
    organizer_type: str | None = None

    # Metadata
    source_id: str | None = None  # ID of the scraper source
    external_url: str | None = None  # URL to original event page
    registration_url: str | None = None  # URL for tickets/registration
    requires_registration: bool = False  # True if registration required (even without URL)
    registration_info: str | None = None  # How to register if no URL (e.g., "Tel: 974... / email@...")
    external_id: str | None = None  # Unique ID from source for deduplication
    image_url: str | None = None  # Approved image (in our Storage)
    source_image_url: str | None = None  # Original image from source (pending approval)

    # Image attribution (for Unsplash compliance)
    image_author: str | None = None  # Photographer name
    image_author_url: str | None = None  # Link to photographer profile
    image_source_url: str | None = None  # Link to original photo page (e.g., Unsplash)

    # Pricing
    is_free: bool | None = None
    price: float | None = None  # Numeric price if available
    price_info: str | None = None  # Full price text (e.g., "Entrada gratuita con reserva")
    alternative_dates: dict | None = None  # Multi-date events: {"dates": ["2026-03-08"], "prices": {"2026-03-08": 305}}

    # Accessibility (structured data for event_accessibility table)
    accessibility: EventAccessibility | None = None
    accessibility_info: str | None = None  # Raw accessibility data (legacy/text)

    # Contact (structured data for event_contact table)
    contact: "EventContact | None" = None

    # Publishing
    is_published: bool = True  # Events published directly
    is_featured: bool = False

    # Recurrence (for recurring events)
    is_recurring: bool = False
    recurrence_rule: dict | None = None  # JSONB: {"frequency": "weekly", "weekDays": ["wednesday"], ...}
    excluded_days: list[str] = Field(default_factory=list)

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: date | None, info) -> date | None:
        """Validate that end_date is after or equal to start_date."""
        if v is not None and "start_date" in info.data:
            start = info.data["start_date"]
            if v < start:
                raise ValueError("end_date must be after or equal to start_date")
        return v

    def generate_external_id(self, source_id: str) -> str:
        """Generate a unique external_id for deduplication."""
        # Combine source + title + date for uniqueness
        key = f"{source_id}:{self.title}:{self.start_date.isoformat()}"
        import hashlib

        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def to_supabase_dict(self) -> dict:
        """Convert to dictionary for Supabase insertion.

        Maps EventCreate fields to Supabase 'events' table columns.
        """
        # Determine if all_day based on time presence
        is_all_day = self.all_day or (self.start_time is None and self.end_time is None)

        # Generate map_url if we have coordinates
        map_url = None
        if self.latitude and self.longitude:
            map_url = f"https://maps.google.com/?q={self.latitude},{self.longitude}"

        data = {
            # Required
            "title": self.title,
            "start_date": self.start_date.isoformat(),

            # Basic info
            "description": self.description,
            "summary": self.summary,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "all_day": is_all_day,

            # Location
            "modality": self.location_type.value,  # Supabase uses 'modality' not 'location_type'
            "venue_name": self.venue_name,
            "address": self.address,
            "district": self.district,
            "city": self.city,
            "province": self.province,
            "comunidad_autonoma": self.comunidad_autonoma,
            "postal_code": self.postal_code,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "map_url": map_url,
            "online_url": self.online_url,

            # Source metadata
            "source_id": self.source_id,
            "external_url": self.external_url,
            "external_id": self.external_id,

            # Images
            "image_url": self.image_url,
            "source_image_url": self.source_image_url,
            "image_author": self.image_author,
            "image_author_url": self.image_author_url,
            "image_source_url": self.image_source_url,

            # Pricing
            "is_free": self.is_free,
            "price": self.price,
            "price_info": self.price_info,

            # Accessibility
            "accessibility_info": self.accessibility_info,

            # Publishing
            "is_published": self.is_published,
            "is_featured": self.is_featured,

            # Recurrence
            "is_recurring": self.is_recurring,
            "recurrence_rule": self.recurrence_rule,
        }

        # Add organizer if present
        if self.organizer:
            data["organizer_name"] = self.organizer.name
            data["organizer_type"] = self.organizer.type.value

        # Remove None values to let Supabase use defaults
        return {k: v for k, v in data.items() if v is not None}


class Event(EventCreate):
    """Full event model with database fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: str | None = None
    updated_at: str | None = None
    created_by: UUID | None = None


class EventBatch(BaseModel):
    """A batch of events from a single scrape run."""

    source_id: str
    source_name: str
    ccaa: str
    scraped_at: str
    events: list[EventCreate]
    total_found: int
    errors: list[str] = Field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Number of successfully parsed events."""
        return len(self.events)

    @property
    def error_count(self) -> int:
        """Number of parsing errors."""
        return len(self.errors)
