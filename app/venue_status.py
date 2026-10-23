from datetime import datetime
from zoneinfo import ZoneInfo


NEPAL_TIMEZONE = ZoneInfo("Asia/Kathmandu")


def venue_status(venue, closures, now=None):
    local_now = (now or datetime.now(NEPAL_TIMEZONE)).astimezone(NEPAL_TIMEZONE)
    today = local_now.date()
    closure = next((item for item in closures if item.closure_date == today), None)
    if closure:
        return False, f"Closed today · {closure.reason}"
    if not venue.is_open:
        return False, "Temporarily closed"
    current = local_now.strftime("%H:%M")
    if current < venue.open_time or current >= venue.close_time:
        return False, f"Closed · opens {venue.open_time}"
    return True, f"Open until {venue.close_time}"
