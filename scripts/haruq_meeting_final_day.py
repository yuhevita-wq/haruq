"""Read-only meeting-date proof for the user-approved HaruQ F1/F2 final-day policy.

Only a netkeirin course-page date navigation entry explicitly marked 最終日
can activate the special F1/F2 ticket selection.  Neither a race's number nor
its round name is proof.  Ambiguous/missing information => no F1/F2 purchase.
"""
from __future__ import annotations

from datetime import date
import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup

from config import NETKEIRIN_BASE_URL

_DATE_LABEL = re.compile(
    r"^(?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12][0-9]|3[01])"
    r"\([^()]{1,5}\)(?P<label>初日|最終日|[2-7]日目)$"
)
_RACE_ID = re.compile(r"race_id=(\d{12})")


def parse_meeting_day(html: str, target_race_id: str) -> dict:
    """Validate exact target race is on this venue's published meeting calendar.

    The event page must contain the exact race ID and an unambiguous
    publication-level date label.  Do NOT infer finality from displayed races,
    current date, number of legs, a final-round race, or the last day scraped.
    """
    if not re.fullmatch(r"\d{12}", target_race_id):
        raise ValueError("Expected 12-digit race ID")
    venue_code = target_race_id[8:10]
    target = date.fromisoformat(
        target_race_id[:4] + "-" + target_race_id[4:6] + "-" + target_race_id[6:8]
    )
    source = f"{NETKEIRIN_BASE_URL}/race/course/?jyo_cd={venue_code}"
    detail = dict(
        is_final_day=None, status="unverified",
        reason=None, meeting_day_label=None,
        source_url=source, source_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        race_id=target_race_id,
    )
    ids = set(_RACE_ID.findall(html))
    if target_race_id not in ids:
        detail["reason"] = "race_not_listed_on_course_calendar"
        return detail

    soup = BeautifulSoup(html, "lxml")
    found = set()
    # The calendar has explicit '10/26 (月) 最終日' labels. Only compact,
    # visible date elements are used; whole-page substring matching would
    # accidentally capture a different meeting.
    for node in soup.find_all(["li", "a", "span", "div", "p", "time"]):
        content = unicodedata.normalize("NFKC", node.get_text(" ", strip=True))
        compact = re.sub(r"\s+", "", content)
        if len(compact) > 36:
            continue
        m = _DATE_LABEL.fullmatch(compact)
        if not m:
            continue
        if (int(m["month"]), int(m["day"])) == (target.month, target.day):
            found.add(m["label"])
    if len(found) != 1:
        detail["reason"] = ("no_explicit_date_label" if not found
                            else "conflicting_date_labels")
        return detail
    label = next(iter(found))
    detail.update(is_final_day=label == "最終日", status="confirmed",
                  meeting_day_label=label, reason=None)
    return detail


def resolve_meeting_day(scraper, target_race_id: str) -> dict:
    venue_code = target_race_id[8:10]
    source = f"{NETKEIRIN_BASE_URL}/race/course/?jyo_cd={venue_code}"
    try:
        html = scraper._get(source)
        return parse_meeting_day(html, target_race_id)
    except Exception as exc:
        return dict(
            is_final_day=None, status="unverified",
            reason=f"schedule_fetch_or_parse_failed:{type(exc).__name__}",
            meeting_day_label=None, source_url=source, source_sha256=None,
            race_id=target_race_id,
        )
