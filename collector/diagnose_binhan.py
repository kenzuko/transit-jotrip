from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

BASE = "https://www.binhanhatien.vn"
DAY = "22/09/2026"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def xhr_headers(referer: str):
    return {
        "Accept": "*/*",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

def dump_html(label: str, html: str):
    print("\n===", label, "len", len(html), "===")
    soup = BeautifulSoup(html, "html.parser")
    text = " | ".join(soup.stripped_strings)
    print("TEXT", text[:12000])
    for el in soup.find_all(["input", "button", "a", "option", "select"]):
        attrs = {k: v for k, v in el.attrs.items() if k in {"id","name","value","class","href","onclick","data-id","data-value","data-trip","data-schedule"}}
        if attrs:
            print("EL", el.name, attrs, "TEXT=", el.get_text(" ", strip=True)[:300])

def main():
    s = requests.Session()
    s.headers.update(HEADERS)

    landing = s.get(BASE + "/dat-ve", headers={"Accept":"text/html,*/*"}, timeout=25)
    print("LANDING", landing.status_code, landing.url, "cookies", s.cookies.get_dict())

    # Booking.js: show only business logic around public endpoints.
    js = s.get(
        BASE + "/Scripts/js/Booking.js",
        headers={
            "Accept": "application/javascript,text/javascript,*/*;q=0.1",
            "Referer": BASE + "/dat-ve",
            "Sec-Fetch-Dest": "script",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
        },
        timeout=25,
    )
    print("BOOKING_JS", js.status_code, len(js.text))
    for needle in [
        "/Home/GetScheduleTripsOfDay",
        "/Home/GetScheduleTripsOfRoundTrip",
        "/Booking/CheckPriceSelectTrip",
        "/thong-tin-phuong-tien",
    ]:
        p = js.text.find(needle)
        print("\nJS_SNIP", needle)
        print(js.text[max(0,p-1800): p+2600] if p >= 0 else "NOT FOUND")

    routes = {
        76: "Phú Quốc-Hà Tiên",
        77: "Hà Tiên-Phú Quốc",
    }

    trip_candidates = []

    for route_id, route_name in routes.items():
        r = s.get(
            BASE + "/Home/GetScheduleTripsOfDay",
            params={
                "tripsId": route_id,
                "day": DAY,
                "tripName": route_name,
                "total": 1,
            },
            headers=xhr_headers(BASE + "/dat-ve"),
            timeout=25,
        )
        print("\nSCHEDULE_REQ", r.url)
        print("SCHEDULE_STATUS", route_id, r.status_code, r.headers.get("content-type"), "len", len(r.text))
        dump_html(f"SCHEDULE {route_id}", r.text)

        soup = BeautifulSoup(r.text, "html.parser")
        for el in soup.find_all(["input","button","a"]):
            blob = " ".join(str(v) for v in el.attrs.values())
            if re.search(r"trip|schedule|select|booking", blob, re.I) or el.get("value"):
                trip_candidates.append((route_id, dict(el.attrs), el.get_text(" ", strip=True)))

    print("\n=== TRIP_CANDIDATES ===")
    for c in trip_candidates[:200]:
        print(c)

    # Extract likely numeric trip IDs from returned markup attributes.
    ids = []
    for _, attrs, _ in trip_candidates:
        for k, v in attrs.items():
            vals = v if isinstance(v, list) else [v]
            for item in vals:
                for m in re.findall(r"(?<!\d)(\d{2,8})(?!\d)", str(item)):
                    n = int(m)
                    if n not in {76,77,2026} and n not in ids:
                        ids.append(n)
    print("LIKELY_TRIP_IDS", ids[:50])

    # Try fare lookup on first plausible returned trip IDs; no purchase/action occurs.
    for trip_id in ids[:8]:
        r = s.get(
            BASE + "/Booking/CheckPriceSelectTrip",
            params={
                "tripId": trip_id,
                "rTripId": 0,
                "slAdult": 1,
                "slElderly": 0,
                "slChildren": 0,
                "slVeterans": 0,
            },
            headers=xhr_headers(BASE + "/dat-ve"),
            timeout=25,
        )
        print("\nPRICE_REQ", r.url)
        print("PRICE_STATUS", trip_id, r.status_code, r.headers.get("content-type"), "len", len(r.text))
        dump_html(f"PRICE {trip_id}", r.text)

if __name__ == "__main__":
    main()
