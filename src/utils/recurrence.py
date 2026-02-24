"""Recurrence utilities for generating event dates.

Supports:
- Weekly: every X weeks on specific days
- Monthly: every X months on specific day or position (first Monday, etc.)
- Daily: every X days
- Yearly: every X years
"""

from datetime import date, timedelta
from typing import Literal


WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

WEEKDAY_NAMES = {v: k for k, v in WEEKDAY_MAP.items()}


def generate_recurrence_dates(
    start_date: date | str,
    rule: dict,
    max_dates: int = 365,
) -> list[str]:
    """Generate recurring dates based on a recurrence rule.

    Args:
        start_date: First occurrence date
        rule: Recurrence rule dict with:
            - frequency: "daily" | "weekly" | "monthly" | "yearly"
            - interval: Every X units (default: 1)
            - weekDays: ["monday", "wednesday"] for weekly
            - monthDay: 15 for monthly (day of month)
            - monthlyPosition: "first" | "second" | ... | "last"
            - monthlyWeekDay: "monday" for monthly position
            - until: "YYYY-MM-DD" end date
            - count: Max number of occurrences
            - except: ["YYYY-MM-DD", ...] dates to exclude
        max_dates: Safety limit

    Returns:
        List of date strings in YYYY-MM-DD format
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    frequency = rule.get("frequency", "weekly")
    interval = rule.get("interval", 1)
    until_str = rule.get("until")
    count = rule.get("count", max_dates)
    except_dates = set(rule.get("except", []))

    until = date.fromisoformat(until_str) if until_str else start_date + timedelta(days=365)
    max_count = min(count, max_dates)

    dates = []

    if frequency == "weekly":
        dates = _generate_weekly(start_date, rule, until, max_count)
    elif frequency == "monthly":
        dates = _generate_monthly(start_date, rule, until, max_count)
    elif frequency == "daily":
        dates = _generate_daily(start_date, interval, until, max_count)
    elif frequency == "yearly":
        dates = _generate_yearly(start_date, interval, until, max_count)

    # Filter out excluded dates
    if except_dates:
        dates = [d for d in dates if d not in except_dates]

    return dates


def _generate_weekly(
    start: date,
    rule: dict,
    until: date,
    max_count: int,
) -> list[str]:
    """Generate weekly recurring dates."""
    week_days = rule.get("weekDays", [])
    interval = rule.get("interval", 1)

    if not week_days:
        # Default to same day as start
        week_days = [WEEKDAY_NAMES[start.weekday()]]

    target_days = [WEEKDAY_MAP[d.lower()] for d in week_days]
    dates = []

    # Find first week start (Monday)
    current = start - timedelta(days=start.weekday())

    while len(dates) < max_count:
        for day_offset in range(7):
            check_date = current + timedelta(days=day_offset)
            if check_date >= start and check_date <= until:
                if check_date.weekday() in target_days:
                    dates.append(check_date.isoformat())
                    if len(dates) >= max_count:
                        break

        current += timedelta(weeks=interval)
        if current > until:
            break

    return dates


def _generate_monthly(
    start: date,
    rule: dict,
    until: date,
    max_count: int,
) -> list[str]:
    """Generate monthly recurring dates."""
    interval = rule.get("interval", 1)
    month_day = rule.get("monthDay")
    position = rule.get("monthlyPosition")  # "first", "second", "third", "fourth", "last"
    week_day = rule.get("monthlyWeekDay")  # "monday", etc.

    dates = []
    current_year = start.year
    current_month = start.month

    while len(dates) < max_count:
        try:
            if month_day:
                # Fixed day of month
                check_date = date(current_year, current_month, month_day)
            elif position and week_day:
                # Position-based (e.g., "first monday")
                check_date = _get_nth_weekday(current_year, current_month, position, week_day)
            else:
                # Default to same day
                check_date = date(current_year, current_month, min(start.day, 28))

            if check_date >= start and check_date <= until:
                dates.append(check_date.isoformat())

        except ValueError:
            pass  # Invalid date (e.g., Feb 30)

        # Move to next month
        current_month += interval
        while current_month > 12:
            current_month -= 12
            current_year += 1

        if date(current_year, current_month, 1) > until:
            break

    return dates


def _get_nth_weekday(year: int, month: int, position: str, weekday: str) -> date:
    """Get the nth weekday of a month (e.g., first monday, last friday)."""
    target_day = WEEKDAY_MAP[weekday.lower()]

    if position == "last":
        # Start from end of month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)

        current = last_day
        while current.weekday() != target_day:
            current -= timedelta(days=1)
        return current
    else:
        # Start from beginning
        position_map = {"first": 1, "second": 2, "third": 3, "fourth": 4}
        n = position_map.get(position, 1)

        first_day = date(year, month, 1)
        # Find first occurrence of target weekday
        days_ahead = target_day - first_day.weekday()
        if days_ahead < 0:
            days_ahead += 7
        first_occurrence = first_day + timedelta(days=days_ahead)

        return first_occurrence + timedelta(weeks=n - 1)


def _generate_daily(
    start: date,
    interval: int,
    until: date,
    max_count: int,
) -> list[str]:
    """Generate daily recurring dates."""
    dates = []
    current = start

    while current <= until and len(dates) < max_count:
        dates.append(current.isoformat())
        current += timedelta(days=interval)

    return dates


def _generate_yearly(
    start: date,
    interval: int,
    until: date,
    max_count: int,
) -> list[str]:
    """Generate yearly recurring dates."""
    dates = []
    current_year = start.year

    while len(dates) < max_count:
        try:
            check_date = date(current_year, start.month, start.day)
            if check_date >= start and check_date <= until:
                dates.append(check_date.isoformat())
        except ValueError:
            pass  # Feb 29 in non-leap year

        current_year += interval
        if current_year > until.year:
            break

    return dates


def build_alternative_dates(
    dates: list[str],
    prices: dict[str, float] | None = None,
) -> dict:
    """Build alternative_dates structure for Supabase.

    Args:
        dates: List of ISO date strings
        prices: Optional dict mapping dates to prices

    Returns:
        {"dates": [...], "prices": {...}} or {"dates": [...]}
    """
    result = {"dates": dates}
    if prices:
        result["prices"] = prices
    return result
