"""Spanish date parsing utilities."""

import re
from datetime import date, datetime, time
from typing import NamedTuple

from dateutil import parser as dateutil_parser

# Spanish month names mapping
SPANISH_MONTHS = {
    "enero": 1,
    "ene": 1,
    "en": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "ab": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "ag": 8,
    "septiembre": 9,
    "sep": 9,
    "sept": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}

# Common date patterns in Spanish websites
DATE_PATTERNS = [
    # "15 de enero de 2025" or "15 enero 2025"
    r"(\d{1,2})\s*(?:de\s*)?(\w+)\s*(?:de\s*)?(\d{4})",
    # "15/01/2025" or "15-01-2025"
    r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})",
    # "2025-01-15" (ISO)
    r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})",
    # "15 ene" or "15 enero" (current year assumed)
    r"(\d{1,2})\s*(?:de\s*)?(\w+)(?:\s|$)",
]

TIME_PATTERNS = [
    # "19:30" or "19:30h"
    r"(\d{1,2}):(\d{2})(?:\s*h)?",
    # "19h30" or "19 h 30"
    r"(\d{1,2})\s*h\s*(\d{2})?",
    # "7:30 PM" or "7:30 pm"
    r"(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)",
]


class DateRange(NamedTuple):
    """A date range with optional times."""

    start_date: date
    end_date: date | None
    start_time: time | None
    end_time: time | None


def parse_spanish_month(month_str: str) -> int | None:
    """Parse Spanish month name to month number.

    Args:
        month_str: Month name in Spanish (e.g., "enero", "ene")

    Returns:
        Month number (1-12) or None if not recognized
    """
    month_lower = month_str.lower().strip()
    return SPANISH_MONTHS.get(month_lower)


def parse_spanish_date(date_str: str, default_year: int | None = None) -> date | None:
    """Parse a Spanish date string into a date object.

    Handles various formats:
    - "15 de enero de 2025"
    - "15 enero 2025"
    - "15/01/2025"
    - "15-01-2025"
    - "2025-01-15"
    - "15 ene" (assumes current/next year)

    Args:
        date_str: Date string in Spanish
        default_year: Year to assume if not specified

    Returns:
        date object or None if parsing failed
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    if default_year is None:
        default_year = datetime.now().year

    # Try pattern: "15 de enero de 2025" or "15 enero 2025"
    match = re.search(
        r"(\d{1,2})\s*(?:de\s*)?(\w+)\s*(?:de\s*)?(\d{4})", date_str, re.IGNORECASE
    )
    if match:
        day = int(match.group(1))
        month = parse_spanish_month(match.group(2))
        year = int(match.group(3))
        if month and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # Try pattern: "15/01/2025" or "15-01-2025"
    match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_str)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Try pattern: "2025-01-15" (ISO)
    match = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", date_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Try pattern: "15 ene" or "15 enero" (no year)
    match = re.search(r"(\d{1,2})\s*(?:de\s*)?(\w+)", date_str, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month = parse_spanish_month(match.group(2))
        if month and 1 <= day <= 31:
            # Use default year, but if date is in the past, use next year
            try:
                parsed = date(default_year, month, day)
                if parsed < datetime.now().date():
                    parsed = date(default_year + 1, month, day)
                return parsed
            except ValueError:
                pass

    # Fallback to dateutil parser
    try:
        parsed = dateutil_parser.parse(date_str, dayfirst=True)
        return parsed.date()
    except (ValueError, TypeError):
        pass

    return None


def parse_time(time_str: str) -> time | None:
    """Parse a time string into a time object.

    Handles formats:
    - "19:30"
    - "19:30h"
    - "19h30"
    - "7:30 PM"

    Args:
        time_str: Time string

    Returns:
        time object or None if parsing failed
    """
    if not time_str:
        return None

    time_str = time_str.strip()

    # Pattern: "19:30" or "19:30h"
    match = re.search(r"(\d{1,2}):(\d{2})(?:\s*h)?", time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    # Pattern: "19h30" or "19 h 30" or "19h"
    match = re.search(r"(\d{1,2})\s*h\s*(\d{2})?", time_str, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    # Pattern: "7:30 PM"
    match = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3).lower()
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    return None


def normalize_date_range(
    start_str: str,
    end_str: str | None = None,
    time_str: str | None = None,
) -> DateRange | None:
    """Parse and normalize a date range.

    Handles various input combinations:
    - Single date: "15 de enero de 2025"
    - Date range: "15 - 20 de enero de 2025"
    - Date with time: "15 de enero a las 19:30"

    Args:
        start_str: Start date string
        end_str: Optional end date string
        time_str: Optional time string

    Returns:
        DateRange or None if parsing failed
    """
    start_date = parse_spanish_date(start_str)
    if not start_date:
        return None

    end_date = parse_spanish_date(end_str) if end_str else None

    # Parse time
    start_time = None
    end_time = None

    if time_str:
        # Check for time range "19:30 - 21:00"
        if " - " in time_str or " a " in time_str:
            parts = re.split(r"\s*[-a]\s*", time_str)
            if len(parts) >= 2:
                start_time = parse_time(parts[0])
                end_time = parse_time(parts[1])
        else:
            start_time = parse_time(time_str)

    return DateRange(
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
    )


def extract_dates_from_text(text: str) -> list[date]:
    """Extract all dates found in a text string.

    Useful for finding dates in event descriptions.

    Args:
        text: Text to search for dates

    Returns:
        List of found dates (may be empty)
    """
    dates: list[date] = []

    # Find all potential date patterns
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            parsed = parse_spanish_date(match.group(0))
            if parsed and parsed not in dates:
                dates.append(parsed)

    return sorted(dates)
