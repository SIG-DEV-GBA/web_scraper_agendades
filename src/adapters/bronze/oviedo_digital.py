"""Oviedo Centros Sociales adapter - All activities from Centro Social Virtual Oviedo.

Source: https://centrosocialvirtualoviedo.es/actividades
Tier: Bronze (HTML, static WordPress/Divi page with tab modules)
CCAA: Principado de Asturias

Parses multiple tab modules:
  Module 0: Actividades en instalaciones (9 category tabs, recurring weekly)
  Module 1: Programa de dinamización (5 tabs, recurring weekly)
  Module 2: Competencias Digitales (5 convocatoria tabs, date-range courses)
  Module 5: Aire libre (6 category tabs, recurring weekly, no venue)

Recurring format: "ACTIVITY\\nVENUE\\nDAY HH:MM-HH:MM"
Digital format: "Title.\\nDel X al Y de Mes de HH:MM a HH:MM h."
"""

import hashlib
import re
from datetime import date, time as dt_time, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventContact, EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

MONTH_NAMES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

DAYS_ES = {
    "lunes": "monday", "martes": "tuesday", "miércoles": "wednesday",
    "miercoles": "wednesday", "jueves": "thursday", "viernes": "friday",
    "sábado": "saturday", "sabado": "saturday", "domingo": "sunday",
}

# ISO weekday: monday=0 ... sunday=6
WEEKDAY_NUM = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Category mapping: tab name -> category_slug
# DB only has: cultural, economica, politica, sanitaria, social, tecnologia
CATEGORY_MAP = {
    # Module 0: Actividades en instalaciones
    "deportivas": "sanitaria",
    "deportivas envejecimiento activo": "sanitaria",
    "baile y expresión corporal": "sanitaria",
    "música y artes escénicas": "cultural",
    "manualidades y artes plásticas": "cultural",
    "costura y artesanía del hilo": "cultural",
    "gastronomía": "social",
    "naturaleza y medioambiente": "social",
    "actividades socioeducativas": "social",
    # Module 1: Programa de dinamización
    "baile": "sanitaria",
    "costura": "cultural",
    "naturaleza": "social",
    "bienestar emocional": "sanitaria",
    "competencias digitales": "tecnologia",
}

# Date pattern for digital courses
DATE_RANGE_RE = re.compile(
    r"Del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{1,2}:\d{2})\s+a\s+(\d{1,2}:\d{2})\s*h",
    re.IGNORECASE,
)

# Time range pattern: "HH:MM-HH:MM" or "HH:MM- HH:MM"
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

# Day pattern: "LUNES", "MARTES Y JUEVES", "LUNES A JUEVES"
DAY_RE = re.compile(
    r"(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
    r"(?:\s+[ya]\s+(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))?",
    re.IGNORECASE,
)

CURRENT_YEAR = date.today().year


def _next_weekday(weekday_en: str) -> date:
    """Get next occurrence of a weekday from today."""
    target = WEEKDAY_NUM.get(weekday_en, 0)
    today = date.today()
    days_ahead = target - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _parse_time(s: str) -> dt_time | None:
    try:
        h, m = s.strip().split(":")
        return dt_time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def _make_id(prefix: str, *parts: str) -> str:
    raw = f"{prefix}_{'_'.join(str(p) for p in parts)}"
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


@register_adapter("oviedo_digital")
class OviedoDigitalAdapter(BaseAdapter):
    """Adapter for all activities from Oviedo Centros Sociales."""

    source_id = "oviedo_digital"
    source_name = "Oviedo - Centros Sociales"
    source_url = "https://centrosocialvirtualoviedo.es/actividades"
    ccaa = "Principado de Asturias"
    ccaa_code = "AS"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    LISTING_URL = "https://centrosocialvirtualoviedo.es/actividades"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = False,
        max_events: int = 500,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch all activities from the page."""
        effective_limit = min(max_events, limit) if limit else max_events

        try:
            self.logger.info("fetching_oviedo", url=self.LISTING_URL)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as client:
                for attempt in range(3):
                    try:
                        response = await client.get(self.LISTING_URL)
                        response.raise_for_status()
                        break
                    except (httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
                        if attempt < 2:
                            self.logger.warning("retry_fetch", attempt=attempt + 1, error=str(e))
                            import asyncio
                            await asyncio.sleep(2 * (attempt + 1))
                        else:
                            raise

            soup = BeautifulSoup(response.text, "html.parser")
            tab_modules = soup.find_all("div", class_="et_pb_tabs")

            events: list[dict[str, Any]] = []

            # Module 0: Actividades en instalaciones (recurring weekly with venue)
            if len(tab_modules) > 0:
                events.extend(self._parse_tab_module(tab_modules[0], has_venue=True))

            # Module 1: Programa de dinamización (recurring weekly with venue)
            if len(tab_modules) > 1:
                events.extend(self._parse_tab_module(tab_modules[1], has_venue=True))

            # Module 2: Competencias Digitales (date-range courses)
            if len(tab_modules) > 2:
                events.extend(self._parse_digital_module(tab_modules[2]))

            # Module 5: Aire libre (recurring weekly, no venue)
            if len(tab_modules) > 5:
                events.extend(self._parse_tab_module(tab_modules[5], has_venue=False, location_note="Al aire libre en Oviedo (ubicación exacta no especificada)"))

            self.logger.info("oviedo_total_events", count=len(events))

            return events[:effective_limit]

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

    # ─── Recurring weekly activities (Modules 0, 1, 5) ───

    def _parse_tab_module(
        self, module: Tag, has_venue: bool = True, location_note: str | None = None,
    ) -> list[dict[str, Any]]:
        """Parse a tab module with recurring weekly activities."""
        events = []
        controls = module.find("ul", class_="et_pb_tabs_controls")
        if not controls:
            return events

        tab_names = [li.get_text(strip=True) for li in controls.find_all("li")]
        all_tabs_div = module.find("div", class_="et_pb_all_tabs")
        if not all_tabs_div:
            return events

        tab_divs = all_tabs_div.find_all("div", class_="et_pb_tab", recursive=False)

        for i, tab_div in enumerate(tab_divs):
            tab_name = tab_names[i] if i < len(tab_names) else f"Tab {i}"
            category = CATEGORY_MAP.get(tab_name.lower(), "social")
            content = tab_div.get_text(separator="\n", strip=True)
            parsed = self._parse_recurring_text(content, tab_name, category, has_venue, location_note)
            events.extend(parsed)

        return events

    def _parse_recurring_text(
        self, text: str, tab_name: str, category: str,
        has_venue: bool, location_note: str | None,
    ) -> list[dict[str, Any]]:
        """Parse recurring activity text.

        Format with venue:  ACTIVITY\\nVENUE_PART(s)\\nDAY HH:MM-HH:MM
        Format without:     ACTIVITY\\nDAY HH:MM-HH:MM
        Venue names can span multiple lines (e.g., "LA" + "FLORIDA").
        Schedule can share a line with venue suffix (e.g., "VEGUÍN JUEVES 9:30-10:30").
        """
        events = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        lines = [l for l in lines if l != "🡢" and not l.startswith("INSCRIPCIONES")]

        # Identify schedule lines (contain both DAY and TIME patterns)
        def _is_schedule(line: str) -> bool:
            return bool(DAY_RE.search(line) and TIME_RE.search(line))

        # Group lines into entries: [non-schedule...] + schedule
        buffer: list[str] = []
        for line in lines:
            if _is_schedule(line):
                # Extract venue suffix before the day name (e.g., "VEGUÍN JUEVES 9:30")
                day_m = DAY_RE.search(line)
                venue_suffix = line[:day_m.start()].strip() if day_m and day_m.start() > 0 else ""
                # Strip "Libre*" marker (means open/free activity)
                venue_suffix = re.sub(r"^Libre\*\s*", "", venue_suffix).strip()
                schedule_text = line[day_m.start():] if day_m else line

                if not buffer:
                    buffer = []
                    continue

                # First buffer line = activity name, rest = venue parts
                activity_name = buffer[0]
                venue_parts = buffer[1:]
                if venue_suffix:
                    venue_parts.append(venue_suffix)

                # For no-venue modules, check for level suffixes (Iniciación/Avanzado)
                if not has_venue and venue_parts:
                    level = venue_parts[0].lower()
                    if level in ("iniciación", "avanzado", "inicio"):
                        activity_name = f"{activity_name} {venue_parts[0]}"
                        venue_parts = venue_parts[1:]

                # Clean activity name
                activity_name = re.sub(r"^Libre\*\s*", "", activity_name).strip()
                if not activity_name or len(activity_name) < 2:
                    buffer = []
                    continue

                # Parse weekdays from schedule
                weekdays = self._extract_weekdays(schedule_text)
                if not weekdays:
                    buffer = []
                    continue

                # Parse times
                time_m = TIME_RE.search(schedule_text)
                start_time = _parse_time(time_m.group(1)) if time_m else None
                end_time = _parse_time(time_m.group(2)) if time_m else None

                # Start date = next occurrence of first weekday
                start_date = _next_weekday(weekdays[0]) if weekdays else date.today()

                # Build venue name
                venue = None
                if has_venue and venue_parts:
                    venue_raw = " ".join(venue_parts).title()
                    venue = f"Centro Social {venue_raw}"

                events.append({
                    "title": activity_name.title(),
                    "start_date": start_date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "venue_name": venue,
                    "category": category,
                    "tab_name": tab_name,
                    "is_recurring": True,
                    "weekdays": weekdays,
                    "location_note": location_note,
                    "source_section": "instalaciones" if has_venue else "aire_libre",
                })

                buffer = []
            else:
                buffer.append(line)

        return events

    def _extract_weekdays(self, schedule_text: str) -> list[str]:
        """Extract English weekday names from a Spanish schedule line."""
        text_lower = schedule_text.lower()

        # Canonical weekday order (no duplicates)
        _WEEKDAY_ORDER = ["lunes", "martes", "miercoles", "jueves", "viernes"]

        # Check for "A" range pattern (LUNES A JUEVES)
        range_match = re.search(
            r"(lunes|martes|mi[eé]rcoles|jueves|viernes)\s+a\s+(lunes|martes|mi[eé]rcoles|jueves|viernes)",
            text_lower,
        )
        if range_match:
            d1 = range_match.group(1).replace("é", "e").replace("á", "a")
            d2 = range_match.group(2).replace("é", "e").replace("á", "a")
            try:
                idx1 = _WEEKDAY_ORDER.index(d1)
                idx2 = _WEEKDAY_ORDER.index(d2)
                return [DAYS_ES[d] for d in _WEEKDAY_ORDER[idx1:idx2 + 1]]
            except ValueError:
                pass

        # Match individual days (e.g., "MARTES Y JUEVES", "LUNES")
        day_match = DAY_RE.search(text_lower)
        if not day_match:
            return []

        day1 = day_match.group(1).replace("é", "e").replace("á", "a")
        day1_en = DAYS_ES.get(day1)
        weekdays = [day1_en] if day1_en else []
        if day_match.group(2):
            day2 = day_match.group(2).replace("é", "e").replace("á", "a")
            day2_en = DAYS_ES.get(day2)
            if day2_en:
                weekdays.append(day2_en)

        return weekdays

    # ─── Competencias Digitales (Module 2) ───

    def _parse_digital_module(self, module: Tag) -> list[dict[str, Any]]:
        """Parse the Competencias Digitales tab module with date-range courses."""
        events = []
        controls = module.find("ul", class_="et_pb_tabs_controls")
        if not controls:
            return events

        all_tabs_div = module.find("div", class_="et_pb_all_tabs")
        if not all_tabs_div:
            return events

        tab_divs = all_tabs_div.find_all("div", class_="et_pb_tab", recursive=False)

        for tab_div in tab_divs:
            content = tab_div.get_text(separator="\n", strip=True)
            parsed = self._parse_digital_courses(content)
            events.extend(parsed)

        return events

    def _parse_digital_courses(self, text: str) -> list[dict[str, Any]]:
        """Parse digital competence courses with Del X al Y format."""
        courses = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        current_center = None
        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect center changes
            if line.lower() == "centro" and i + 1 < len(lines):
                nxt = lines[i + 1]
                if "magdalena" in nxt.lower():
                    current_center = "villa magdalena"
                    i += 2
                    continue
                elif "corredoria" in nxt.lower():
                    current_center = "la corredoria"
                    i += 2
                    continue

            # Skip non-course lines
            if any(line.lower().startswith(p) for p in [
                "convocatoria", "oferta presencial", "tfno:", "centro social",
                "c.j. y telecentro", "al margen", "de manera", "formulario",
            ]):
                i += 1
                continue

            # Match date on current line
            dm = DATE_RANGE_RE.search(line)
            if dm:
                title_part = line[:dm.start()].strip().rstrip(".")
                if not title_part and i > 0:
                    title_part = lines[i - 1].rstrip(".")
                course = self._build_digital_course(title_part, dm, current_center)
                if course:
                    courses.append(course)
                i += 1
                continue

            # Check next line for date
            if i + 1 < len(lines):
                dm2 = DATE_RANGE_RE.search(lines[i + 1])
                if dm2:
                    title = line.rstrip(".")
                    course = self._build_digital_course(title, dm2, current_center)
                    if course:
                        courses.append(course)
                    i += 2
                    continue

            i += 1

        return courses

    def _build_digital_course(
        self, title: str, dm: re.Match, center_key: str | None,
    ) -> dict[str, Any] | None:
        if not title or len(title) < 3:
            return None

        day_start = int(dm.group(1))
        day_end = int(dm.group(2))
        month = MONTHS_ES.get(dm.group(3).lower())
        if not month:
            return None

        try:
            start_date = date(CURRENT_YEAR, month, day_start)
            end_date = date(CURRENT_YEAR, month, day_end)
            start_time = _parse_time(dm.group(4))
            end_time = _parse_time(dm.group(5))
        except (ValueError, TypeError):
            return None

        centers = {
            "villa magdalena": ("Centro Social Villa Magdalena", "Avda. de Galicia, nº 36"),
            "la corredoria": ("C.J. y Telecentro La Corredoria", "Calle José Requejo, nº 16"),
        }
        venue_name, address = centers.get(center_key, (None, None)) if center_key else (None, None)

        return {
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "end_time": end_time,
            "venue_name": venue_name,
            "address": address,
            "category": "tecnologia",
            "tab_name": "Competencias Digitales",
            "is_recurring": False,
            "weekdays": None,
            "location_note": None,
            "source_section": "competencias_digitales",
        }

    # ─── parse_event ───

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")
            if not title or not start_date:
                return None

            category = raw_data.get("category", "social")
            is_recurring = raw_data.get("is_recurring", False)
            weekdays = raw_data.get("weekdays")
            section = raw_data.get("source_section", "")

            # Build description
            tab_name = raw_data.get("tab_name", "")
            start_time = raw_data.get("start_time")
            end_time = raw_data.get("end_time")
            time_str = f"de {start_time.strftime('%H:%M')} a {end_time.strftime('%H:%M')}" if start_time and end_time else ""

            if is_recurring and weekdays:
                day_names_es = {v: k.title() for k, v in DAYS_ES.items()}
                dias = ", ".join(day_names_es.get(d, d) for d in weekdays)
                desc_parts = [
                    f"Actividad semanal de la Red de Centros Sociales de Oviedo.",
                    f"Categoria: {tab_name}.",
                    f"Horario: {dias} {time_str}." if time_str else f"Dias: {dias}.",
                    "Actividad gratuita. Inscripcion presencial en el centro.",
                ]
                if raw_data.get("location_note"):
                    desc_parts.append(raw_data["location_note"])
            else:
                end_date = raw_data.get("end_date")
                mes = MONTH_NAMES_ES.get(start_date.month, "")
                date_str = f"Del {start_date.day} al {end_date.day} de {mes}" if end_date else ""
                desc_parts = [
                    f"Curso de competencias digitales del programa «Oviedo, Ciudadania Digital».",
                    f"Formacion presencial y gratuita {time_str}.",
                    date_str,
                    "Inscripcion presencial en el centro o llamando al 625 346 237.",
                ]

            description = "\n".join(p for p in desc_parts if p)

            # Recurrence rule
            recurrence_rule = None
            if is_recurring and weekdays:
                recurrence_rule = {"frequency": "weekly", "weekDays": weekdays}

            # External ID
            ext_parts = [title, str(start_date)]
            if start_time:
                ext_parts.append(start_time.strftime("%H%M"))
            if raw_data.get("venue_name"):
                ext_parts.append(raw_data["venue_name"])
            external_id = _make_id("oviedo", *ext_parts)

            organizer = EventOrganizer(
                name="Ayuntamiento de Oviedo - Red de Centros Sociales",
                url="https://centrosocialvirtualoviedo.es",
                type="institucion",
            )

            contact = EventContact(
                phone="625 346 237",
                email="actividadesoviedo@arteaula.com",
                info="De 9 a 14h y de 16 a 17h",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=raw_data.get("end_date"),
                start_time=start_time,
                end_time=end_time,
                description=description,
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                city="Oviedo",
                province="Asturias",
                comunidad_autonoma="Principado de Asturias",
                country="España",
                location_type=LocationType.PHYSICAL,
                location_details=raw_data.get("location_note"),
                external_url=self.LISTING_URL,
                external_id=external_id,
                source_id=self.source_id,
                category_slugs=[category],
                organizer=organizer,
                contact=contact,
                is_free=True,
                is_recurring=is_recurring,
                recurrence_rule=recurrence_rule,
                requires_registration=True,
                registration_info="Inscripcion presencial en el centro. Tel: 625 346 237",
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
