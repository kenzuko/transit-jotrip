from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "network.json"
BUS_CONFIG = ROOT / "config" / "bus_public.json"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")

HEADERS = {
    "User-Agent": "JoTrip-Transit/1.0 (+https://transit.openphuquoc.com; public schedule monitor)",
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT = 20  # keep upstream requests bounded

SOURCES = {
    "thanh_thoi": "https://thanhthoi.vn/?lg=vi",
    "superdong": "https://online.superdong.com.vn/Home/ScheduleBoat",
}

ROUTES = [
    ("Phú Quốc", "Hà Tiên"),
    ("Hà Tiên", "Phú Quốc"),
    ("Phú Quốc", "Rạch Giá"),
    ("Rạch Giá", "Phú Quốc"),
]


def fold(value: str) -> str:
    s = unicodedata.normalize("NFD", value or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def norm_dash(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("–", "-").replace("—", "-")).strip()


def route_from_text(value: str):
    hay = fold(norm_dash(value))
    for origin, destination in ROUTES:
        needle = f"{fold(origin)} - {fold(destination)}"
        if needle in hay:
            return origin, destination
    return None


def times_from_text(value: str):
    found = []
    for h, m in re.findall(r"(?<!\d)([01]?\d|2[0-3])\s*[:hH]\s*([0-5]\d)(?!\d)", value or ""):
        found.append(f"{int(h):02d}:{m}")
    return found


def iso_at(day: str, hhmm: str):
    d = datetime.strptime(day, "%Y-%m-%d")
    h, m = map(int, hhmm.split(":"))
    return d.replace(hour=h, minute=m, tzinfo=TZ).isoformat()


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def parsed_day_from_thanh_thoi(strings):
    for s in strings[:80]:
        m = re.search(r"Ngày\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})", s, flags=re.I)
        if m:
            dd, mm, yyyy = map(int, m.groups())
            return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    return datetime.now(TZ).strftime("%Y-%m-%d")


def parse_thanh_thoi(html: str):
    soup = BeautifulSoup(html, "html.parser")
    strings = list(soup.stripped_strings)
    day = parsed_day_from_thanh_thoi(strings)
    rows = []
    seen = set()

    for i, token in enumerate(strings):
        route = route_from_text(token)
        if not route:
            continue
        origin, destination = route
        times = []
        status = None
        vessel = None

        for nxt in strings[i + 1 : min(len(strings), i + 15)]:
            if route_from_text(nxt):
                break
            for t in times_from_text(nxt):
                if t not in times:
                    times.append(t)
            f = fold(nxt)
            if "da xuat ben" in f:
                status = "Đã xuất bến"
            elif "dat ve" in f and status is None:
                status = "Mở bán"
            m = re.search(r"Thriving\s+[A-Za-z0-9.-]+", nxt, flags=re.I)
            if m:
                vessel = m.group(0)

        if not times:
            continue
        dep = times[0]
        arr = times[1] if len(times) > 1 else None
        key = ("Thạnh Thới", origin, destination, day, dep)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "type": "sea",
                "mode": "FERRY",
                "operator": "Thạnh Thới",
                "origin": origin,
                "destination": destination,
                "departure_time": iso_at(day, dep),
                "arrival_time": iso_at(day, arr) if arr else None,
                "vessel_or_service": vessel or "Thạnh Thới",
                "status": status or "Theo lịch công bố",
                "data_kind": "operational_public",
                "source_label": "Thạnh Thới public schedule",
                "source_url": SOURCES["thanh_thoi"],
                "confidence": "high" if status else "medium",
            }
        )
    return rows


def parse_superdong(html: str):
    soup = BeautifulSoup(html, "html.parser")
    strings = list(soup.stripped_strings)
    day = datetime.now(TZ).strftime("%Y-%m-%d")
    rows = []
    seen = set()

    for i, token in enumerate(strings):
        route = route_from_text(token)
        if not route:
            continue
        origin, destination = route
        times = []
        for nxt in strings[i + 1 : min(len(strings), i + 14)]:
            if route_from_text(nxt):
                break
            if fold(nxt).startswith("tuyen ") and times:
                break
            for t in times_from_text(nxt):
                if t not in times:
                    times.append(t)
            if len(times) >= 6:
                break

        for dep in times:
            key = ("Superdong", origin, destination, day, dep)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "type": "sea",
                    "mode": "FAST FERRY",
                    "operator": "Superdong",
                    "origin": origin,
                    "destination": destination,
                    "departure_time": iso_at(day, dep),
                    "arrival_time": None,
                    "vessel_or_service": "Superdong",
                    "status": "Theo lịch công bố",
                    "data_kind": "schedule",
                    "source_label": "Superdong public schedule",
                    "source_url": SOURCES["superdong"],
                    "confidence": "medium",
                }
            )
    return rows


def load_bus_services():
    data = json.loads(BUS_CONFIG.read_text(encoding="utf-8"))
    services = []
    for row in data.get("services", []):
        item = dict(row)
        item["source_label"] = data["source"]["label"]
        item["source_url"] = data["source"]["url"]
        item["verified_at"] = data.get("verified_at")
        services.append(item)
    return services, data


def unique_routes(departures, services):
    keys = set()
    for r in departures:
        keys.add((r.get("type"), r.get("origin"), r.get("destination")))
    for r in services:
        keys.add((r.get("type"), r.get("origin"), r.get("destination")))
    return len(keys)


def main():
    now = datetime.now(TZ)
    source_state = {}
    errors = []
    departures = []

    try:
        html = fetch(SOURCES["thanh_thoi"])
        tt = parse_thanh_thoi(html)
        departures.extend(tt)
        source_state["thanh_thoi"] = {
            "label": "Thạnh Thới public operational schedule",
            "status": "ok" if tt else "empty",
            "records": len(tt),
            "data_kind": "operational_public",
            "url": SOURCES["thanh_thoi"],
        }
    except Exception as exc:
        source_state["thanh_thoi"] = {"label": "Thạnh Thới", "status": "error", "records": 0}
        errors.append(f"Thạnh Thới: {exc}")

    try:
        html = fetch(SOURCES["superdong"])
        sd = parse_superdong(html)
        departures.extend(sd)
        source_state["superdong"] = {
            "label": "Superdong public schedule",
            "status": "ok" if sd else "empty",
            "records": len(sd),
            "data_kind": "schedule",
            "url": SOURCES["superdong"],
        }
    except Exception as exc:
        source_state["superdong"] = {"label": "Superdong", "status": "error", "records": 0}
        errors.append(f"Superdong: {exc}")

    services, bus_meta = load_bus_services()
    source_state["bus"] = {
        "label": bus_meta["source"]["label"],
        "status": "ok",
        "records": len(services),
        "data_kind": "schedule_frequency",
        "url": bus_meta["source"]["url"],
        "verified_at": bus_meta.get("verified_at"),
    }

    departures.sort(key=lambda x: x.get("departure_time") or "")

    sea_ok = any(x.get("type") == "sea" for x in departures)
    bus_ok = bool(services)
    healthy_sources = sum(1 for k in ("thanh_thoi", "superdong", "bus") if source_state.get(k, {}).get("status") == "ok")

    if healthy_sources == 3:
        health_status = "good"
        network_label = "DATA ONLINE"
        health_desc = "Nguồn công khai đang đọc được. Trạng thái được giữ đúng cấp độ Actual / Schedule / Frequency."
    elif healthy_sources:
        health_status = "watch"
        network_label = "PARTIAL DATA"
        health_desc = "Một phần nguồn đang thiếu hoặc thay đổi cấu trúc. Không suy diễn trạng thái từ dữ liệu thiếu."
    else:
        health_status = "bad"
        network_label = "NO DATA"
        health_desc = "Không đọc được nguồn vận hành."

    alerts = [
        {
            "type": "data",
            "title": "Nguồn dữ liệu cần kiểm tra",
            "description": e[:220],
            "severity": "watch",
        }
        for e in errors
    ]

    payload = {
        "schema_version": "1.1",
        "ready": bool(departures or services),
        "generated_at": now.isoformat(),
        "summary": {
            "network": {"label": network_label},
            "sea": {
                "label": "Có dữ liệu" if sea_ok else "Chưa có dữ liệu",
                "description": "Thạnh Thới: trạng thái công khai. Superdong: lịch công bố."
            },
            "bus": {
                "label": "Có lịch công bố" if bus_ok else "Chưa có dữ liệu",
                "description": "Tuyến VinBus công khai, hiện ở cấp Schedule/Frequency."
            },
            "active_routes": unique_routes(departures, services),
        },
        "sources": {
            "sea": {
                "label": "Thạnh Thới + Superdong",
                "freshness": "mixed",
            },
            "bus": {
                "label": bus_meta["source"]["label"],
                "freshness": f"verified {bus_meta.get('verified_at')}",
            },
            "registry": source_state,
            "phu_quoc_express": {
                "label": "Phú Quốc Express public monthly schedule",
                "status": "reference_only",
                "data_kind": "schedule_image",
                "note": "Booking system excluded from automated collection due to published non-commercial-use terms.",
                "url": "https://phuquocexpress.com/lichtaucactuyen",
            },
        },
        "health": {
            "status": health_status,
            "description": health_desc,
            "source_errors": errors,
        },
        "departures": departures,
        "services": services,
        "alerts": alerts,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"generated={payload['generated_at']}")
    print(f"departures={len(departures)} services={len(services)} health={health_status}")
    for key, val in source_state.items():
        print(f"source={key} status={val.get('status')} records={val.get('records')}")
    if errors:
        for err in errors:
            print(f"warning={err}", file=sys.stderr)


if __name__ == "__main__":
    main()
