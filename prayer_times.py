import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, date, timedelta
import pytz
import uuid
import os
import subprocess
import re
from playwright.sync_api import sync_playwright

SYDNEY_TZ = pytz.timezone("Australia/Sydney")

KNOWN_PRAYERS = {"Fajr", "Zuhr", "Asr", "Maghrib", "Esha"}

PRAYER_NAME_MAP = {
    # gopray name → aladhan key
    "Fajr": "Fajr",
    "Zuhr": "Dhuhr",
    "Asr": "Asr",
    "Maghrib": "Maghrib",
    "Esha": "Isha",
}

PRAYER_ADJUSTMENTS = {
    "Fajr": -15, 
}

def scrape_gopray(url):
    """Scrape raw time strings from a gopray.com.au mosque page."""
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    times = {}

    prayer_table = soup.select_one("div.place-prayer-times table")
    if not prayer_table:
        print("Warning: couldn't find prayer times table")
        return times

    for row in prayer_table.select("tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            name = th.text.strip()
            time = td.text.strip()
            if name in KNOWN_PRAYERS:
                times[name] = time

    return times

def get_aladhan_times(suburb="Minto", country="Australia", method=2):
    """Fallback: get calculated prayer times from Aladhan API."""
    today = date.today()
    url = "https://api.aladhan.com/v1/timingsByAddress"
    params = {
        "address": f"{suburb}, NSW, {country}",
        "method": method, 
        "date": today.strftime("%d-%m-%Y"),
    }
    r = requests.get(url, params=params)
    data = r.json()["data"]["timings"]
    return data  


def parse_offset(time_str):
    """Extract minute offset from strings like '20 mins after athaan'."""
    match = re.search(r"(\d+)\s*mins?\s*after", time_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def resolve_times(scraped_times: dict, fallback_suburb="Minto") -> dict:
    """
    Resolve raw scraped strings into datetime objects.
    Falls back to Aladhan API for 'X mins after athaan' / 'just after athaan' entries.
    Returns {prayer_name: datetime} — naive datetimes, date portion is today.
    """
    aladhan = None  
    resolved = {}

    for prayer, raw_time in scraped_times.items():
        offset = parse_offset(raw_time)

        if offset is not None:
            if aladhan is None:
                aladhan = get_aladhan_times(fallback_suburb)
            aladhan_key = PRAYER_NAME_MAP.get(prayer)
            if aladhan_key and aladhan_key in aladhan:
                base = datetime.strptime(aladhan[aladhan_key], "%H:%M")
                base += timedelta(minutes=PRAYER_ADJUSTMENTS.get(prayer, 0))
                resolved[prayer] = base + timedelta(minutes=offset)
            else:
                print(f"Warning: couldn't resolve Aladhan fallback for {prayer}")

        elif re.search(r"just after athaan", raw_time, re.IGNORECASE):
            if aladhan is None:
                aladhan = get_aladhan_times(fallback_suburb)
            aladhan_key = PRAYER_NAME_MAP.get(prayer)
            if aladhan_key:
                base = datetime.strptime(aladhan[aladhan_key], "%H:%M")
                base += timedelta(minutes=PRAYER_ADJUSTMENTS.get(prayer, 0))
                resolved[prayer] = base
            else:
                print(f"Warning: couldn't resolve Aladhan fallback for {prayer}")

        else:
            try:
                resolved[prayer] = datetime.strptime(raw_time, "%I:%M %p")
            except ValueError:
                print(f"Warning: couldn't parse time '{raw_time}' for {prayer}")

    return resolved


def build_ics(sources: list[tuple[str, dict]]) -> bytes:
    """
    Build an .ics calendar file from resolved prayer times.
    sources: list of (mosque_name, {prayer_name: datetime}) tuples
             where datetime is a naive datetime (time only, date = today).
    """
    cal = Calendar()
    cal.add("prodid", "-//Prayer Times//EN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Prayer Times")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "P1D")

    today = date.today()

    for mosque_name, times in sources:
        for prayer_name, naive_dt in times.items():
            dt = naive_dt.replace(year=today.year, month=today.month, day=today.day)
            dt = SYDNEY_TZ.localize(dt)

            event = Event()
            event.add("summary", f"🕌 {prayer_name} - {mosque_name}")
            event.add("dtstart", dt)
            event.add("dtend", dt + timedelta(minutes=20))
            event.add("uid", str(uuid.uuid4()))
            cal.add_component(event)

    return cal.to_ical()

def main():
    print("Scraping Minto Mosque from gopray...")
    minto_raw      = scrape_gopray("https://gopray.com.au/place/minto-suburban-islamic-centre-mosque/")
    minto_resolved = resolve_times(minto_raw, fallback_suburb="Minto")

    print("Scraping Daar Ibn Umar...")
    daar_raw       = scrape_gopray("https://gopray.com.au/place/campbelltown-dar-ibn-omar/")
    daar_resolved  = resolve_times(daar_raw, fallback_suburb="Campbelltown")

    ics_data = build_ics([
        ("Minto Mosque",  minto_resolved),
        ("Daar Ibn Umar", daar_resolved),
    ])

    output_path = os.path.expanduser("~/prayer-times-calendar/prayer_times.ics")
    with open(output_path, "wb") as f:
        f.write(ics_data)
    print(f"Saved to {output_path}")

    repo_path = os.path.expanduser("~/prayer-times-calendar")
    subprocess.run(["git", "-C", repo_path, "add", "prayer_times.ics"], check=True)
    subprocess.run(["git", "-C", repo_path, "commit", "-m", f"Prayer times {date.today()}"], check=True)
    subprocess.run(["git", "-C", repo_path, "push"], check=True)
    print("Pushed to GitHub")

if __name__ == "__main__":
    main()