from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://www.binhanhatien.vn"
DAY = "22/09/2026"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

KEYWORDS = re.compile(r"(ajax|fetch\(|axios|\.get\(|\.post\(|url\s*:|schedule|price|fare|route|booking|ticket|vehicle|motor|moto|car|oto|phuong-tien|giá|gia|chuyến|chuyen)", re.I)

def xhr_headers(referer: str):
    return {
        "Accept": "*/*",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

def dump_relevant(label: str, html: str):
    print("\n===", label, "len", len(html), "===")
    soup = BeautifulSoup(html, "html.parser")
    text = " | ".join(soup.stripped_strings)
    print("TEXT", text[:15000])
    for el in soup.find_all(["input","select","option","button","a","form"]):
        attrs = {k:v for k,v in el.attrs.items() if k in {
            "id","name","value","class","href","onclick","action","method",
            "data-id","data-value","data-trip","data-schedule","data-hourgo",
            "data-nametrips","disabled","checked","type"
        }}
        if attrs:
            t = el.get_text(" ", strip=True)[:240]
            print("EL", el.name, attrs, "TEXT=", t)
    return soup

def inspect_scripts(s: requests.Session, page_url: str, soup: BeautifulSoup):
    for sc in soup.find_all("script"):
        src = sc.get("src")
        if not src:
            txt = sc.get_text("\n", strip=False)
            if KEYWORDS.search(txt or ""):
                print("INLINE_JS_BEGIN")
                print((txt or "")[:18000])
                print("INLINE_JS_END")
            continue
        full = urljoin(page_url, src)
        host = urlparse(full).hostname or ""
        if host not in {"www.binhanhatien.vn","binhanhatien.vn"}:
            continue
        h = {
            "Accept": "application/javascript,text/javascript,*/*;q=0.1",
            "Referer": page_url,
            "Sec-Fetch-Dest": "script",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
        }
        try:
            r = s.get(full, headers=h, timeout=25)
            print("SCRIPT", full, "status", r.status_code, "ctype", r.headers.get("content-type"), "len", len(r.text))
            if KEYWORDS.search(r.text or ""):
                for line in r.text.splitlines():
                    if KEYWORDS.search(line):
                        print("SCRIPT_MATCH", line[:2400])
        except Exception as exc:
            print("SCRIPT_ERROR", full, repr(exc))

def main():
    s = requests.Session()
    s.headers.update(HEADERS)
    landing = s.get(BASE + "/dat-ve", headers={"Accept":"text/html,*/*"}, timeout=25)
    print("LANDING", landing.status_code, landing.url, "cookies", s.cookies.get_dict())

    routes = {
        76: "Phú Quốc-Hà Tiên",
        77: "Hà Tiên-Phú Quốc",
    }
    trips = []

    for route_id, route_name in routes.items():
        r = s.get(
            BASE + "/Home/GetScheduleTripsOfDay",
            params={"tripsId":route_id,"day":DAY,"tripName":route_name,"total":1},
            headers=xhr_headers(BASE + "/dat-ve"),
            timeout=25,
        )
        print("\nSCHEDULE_REQ", r.url)
        print("SCHEDULE_STATUS", route_id, r.status_code, r.headers.get("content-type"), "len", len(r.text))
        soup = dump_relevant(f"SCHEDULE {route_id}", r.text)
        for radio in soup.select("input[name='tripOne']"):
            trip_id = radio.get("value")
            parent = radio.find_parent()
            ancestors = []
            cur = radio
            for _ in range(5):
                cur = cur.parent
                if not cur:
                    break
                ancestors.append({
                    "tag": cur.name,
                    "attrs": dict(cur.attrs),
                    "text": cur.get_text(" ", strip=True)[:600],
                })
            print("TRIP_MARKUP", route_id, trip_id, ancestors)
            # Parse first two hh:mm occurrences in a compact text block around the radio.
            block = radio.find_parent("li") or radio.find_parent("div") or parent
            bt = block.get_text(" ", strip=True) if block else ""
            times = re.findall(r"(?<!\d)([0-2]?\d)\s*:\s*([0-5]\d)(?!\d)", bt)
            hhmm = [f"{int(h):02d}:{m}" for h,m in times]
            trips.append({
                "route_id": route_id,
                "route_name": route_name,
                "trip_id": int(trip_id),
                "times": hhmm,
            })

    print("\nTRIPS", trips)

    # Read price for each returned trip. Public read only.
    for t in trips:
        r = s.get(
            BASE + "/Booking/CheckPriceSelectTrip",
            params={
                "tripId":t["trip_id"],"rTripId":0,
                "slAdult":1,"slElderly":0,"slChildren":0,"slVeterans":0,
            },
            headers=xhr_headers(BASE + "/dat-ve"),
            timeout=25,
        )
        print("\nPRICE", t["trip_id"], r.status_code, r.url, "len", len(r.text))
        dump_relevant(f"PRICE {t['trip_id']}", r.text)

    # Only inspect one currently offered trip's public vehicle step.
    target = next((t for t in trips if t["route_id"] == 77), trips[0] if trips else None)
    if not target:
        return
    hgo = target["times"][0] if target["times"] else "12:25"
    params = {
        "tripId": target["trip_id"],
        "nTrip": target["route_name"],
        "nRTrip": "",
        "rTripId": 0,
        "slAdult": 1,
        "slElderly": 0,
        "slChildren": 0,
        "slVeterans": 0,
        "dGo": DAY,
        "hGo": hgo,
        "dRGo": "",
        "hRGo": "",
        "nMoto": 1,
        "nOto": 0,
    }
    r = s.get(
        BASE + "/thong-tin-phuong-tien",
        params=params,
        headers={"Accept":"text/html,application/xhtml+xml,*/*","Referer":BASE+"/dat-ve"},
        timeout=25,
        allow_redirects=True,
    )
    print("\nVEHICLE_REQ", r.url)
    print("VEHICLE_STATUS", r.status_code, r.headers.get("content-type"), "final", r.url, "history", [(x.status_code,x.headers.get("location")) for x in r.history], "len", len(r.text))
    soup = dump_relevant("VEHICLE_PAGE", r.text)
    for sel in soup.select("select.TypePrice"):
        print("VEHICLE_SELECT_OUTER", str(sel))
        print("VEHICLE_SELECT_OPTIONS", [
            {"text": opt.get_text(" ", strip=True), "attrs": dict(opt.attrs)}
            for opt in sel.find_all("option")
        ])
        parent = sel.find_parent(class_=re.compile(r"Form(?:Moto|Oto)Infor")) or sel.parent
        print("VEHICLE_FORM_BLOCK", str(parent)[:12000])
    inspect_scripts(s, r.url, soup)

if __name__ == "__main__":
    main()
