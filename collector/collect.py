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
    "superdong": "https://online.superdong.com.vn/Booking",
    "phu_quoc_express": "https://online.phuquocexpress.com/",
}

PQE_ROUTES = {
    1: ("Rạch Giá", "Phú Quốc"),
    2: ("Phú Quốc", "Rạch Giá"),
    3: ("Hà Tiên", "Phú Quốc"),
    4: ("Phú Quốc", "Hà Tiên"),
}

SUPERDONG_ROUTES = {
    3: ("Hà Tiên", "Phú Quốc"),
    4: ("Phú Quốc", "Hà Tiên"),
    5: ("Rạch Giá", "Phú Quốc"),
    6: ("Phú Quốc", "Rạch Giá"),
}


# Day-board contract: only date-specific sea rows may be presented as a selected-day departure.
FARE_CATALOG = {
    ("Thạnh Thới", "Hà Tiên", "Phú Quốc"): {
        "adult": 205000,
        "vehicle": {"motorbike": 95000, "motorcycle": 240000, "car_4_5_seat": 1000000, "pickup_4_seat": 1300000},
        "vehicle_summary": "Xe máy 95.000đ · ô tô 4-5 chỗ từ 1.000.000đ",
        "currency": "VND",
        "checked_at": "2026-09-21",
        "source_url": "https://thanhthoi.vn/?lg=vi",
    },
    ("Thạnh Thới", "Phú Quốc", "Hà Tiên"): {
        "adult": 205000,
        "vehicle": {"motorbike": 95000, "motorcycle": 240000, "car_4_5_seat": 1000000, "pickup_4_seat": 1300000},
        "vehicle_summary": "Xe máy 95.000đ · ô tô 4-5 chỗ từ 1.000.000đ",
        "currency": "VND",
        "checked_at": "2026-09-21",
        "source_url": "https://thanhthoi.vn/?lg=vi",
    },
    ("Thạnh Thới", "Rạch Giá", "Phú Quốc"): {
        "adult": 315000,
        "vehicle": {"motorbike": 165000, "car_4_5_seat": 1500000, "pickup_4_seat": 1550000},
        "vehicle_summary": "Xe máy 165.000đ · ô tô 4-5 chỗ từ 1.500.000đ",
        "currency": "VND",
        "checked_at": "2026-09-21",
        "source_url": "https://thanhthoi.vn/?lg=vi",
    },
    ("Thạnh Thới", "Phú Quốc", "Rạch Giá"): {
        "adult": 315000,
        "vehicle": {"motorbike": 165000, "car_4_5_seat": 1500000, "pickup_4_seat": 1550000},
        "vehicle_summary": "Xe máy 165.000đ · ô tô 4-5 chỗ từ 1.500.000đ",
        "currency": "VND",
        "checked_at": "2026-09-21",
        "source_url": "https://thanhthoi.vn/?lg=vi",
    },
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


def fare_for(operator: str, origin: str, destination: str):
    fare = FARE_CATALOG.get((operator, origin, destination))
    return dict(fare) if fare else None


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def fetch_json(url: str, params=None):
    headers = dict(HEADERS)
    headers["Accept"] = "application/json,text/plain,*/*"
    r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def pqe_fare_for(route_id: int, boat_type_id: int, day: str):
    url = SOURCES["phu_quoc_express"].rstrip("/") + "/Booking/GetTicketPrice"
    data = fetch_json(
        url,
        {
            "RouteId": route_id,
            "BoatTypeId": boat_type_id,
            "DepartDate": day,
        },
    )
    adult_classes = {}
    child_classes = {}
    senior_classes = {}
    for row in data if isinstance(data, list) else []:
        ticket_type = row.get("TicketTypeId")
        ticket_class = str(row.get("TicketClass") or "").upper()
        price = row.get("PriceWithVAT")
        if price is None:
            continue
        if ticket_type == 1:
            adult_classes[ticket_class or "STANDARD"] = price
        elif ticket_type == 2:
            child_classes[ticket_class or "STANDARD"] = price
        elif ticket_type == 3:
            senior_classes[ticket_class or "STANDARD"] = price
    adult = adult_classes.get("ECO")
    if adult is None and adult_classes:
        adult = min(adult_classes.values())
    return {
        "adult": adult,
        "adult_classes": adult_classes,
        "child_classes": child_classes,
        "senior_classes": senior_classes,
        "currency": "VND",
        "checked_at": day,
        "source_url": SOURCES["phu_quoc_express"],
    }


def collect_phu_quoc_express(day: str):
    base = SOURCES["phu_quoc_express"].rstrip("/")
    rows = []
    fare_cache = {}
    for route_id, (origin, destination) in PQE_ROUTES.items():
        voyages = fetch_json(
            base + "/Booking/SearchVoyage",
            {
                "RouteId": route_id,
                "DepartDate": day,
                "NoOfPassenger": 1,
            },
        )
        for voyage in voyages if isinstance(voyages, list) else []:
            dep = voyage.get("DepartTime")
            if not dep:
                continue
            boat_type_id = voyage.get("BoatTypeId")
            fare_key = (route_id, boat_type_id)
            if fare_key not in fare_cache:
                try:
                    fare_cache[fare_key] = pqe_fare_for(route_id, boat_type_id, day)
                except Exception:
                    fare_cache[fare_key] = None
            rows.append(
                {
                    "type": "sea",
                    "mode": "FAST FERRY",
                    "operator": "Phú Quốc Express",
                    "origin": origin,
                    "destination": destination,
                    "departure_time": iso_at(day, dep),
                    "arrival_time": None,
                    "vessel_or_service": voyage.get("BoatNm") or "Phú Quốc Express",
                    "harbor": voyage.get("Harbor"),
                    "status": "Cập nhật theo ngày",
                    "data_kind": "date_specific_booking",
                    "date_specific": True,
                    "service_date_basis": "date_specific_booking",
                    "source_label": "Nguồn chính thức",
                    "source_url": SOURCES["phu_quoc_express"],
                    "confidence": "high",
                    "fare": fare_cache.get(fare_key),
                }
            )
    return rows


def superdong_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    session.headers.update(
        {
            "Accept": "application/json,text/javascript,*/*;q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": SOURCES["superdong"],
        }
    )
    # Establish the same public booking session/cookies as a normal visitor.
    landing_headers = dict(HEADERS)
    landing_headers["Referer"] = "https://www.superdong.com.vn/"
    r = session.get(SOURCES["superdong"], headers=landing_headers, timeout=TIMEOUT)
    r.raise_for_status()
    return session


def superdong_get_json(session, path: str, params=None):
    base = "https://online.superdong.com.vn"
    r = session.get(base + path, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def superdong_fare_for(session, route_id: int, day: str):
    data = superdong_get_json(
        session,
        "/api/Route/GetFare",
        {
            "NoOfPassenger": 1,
            "RouteId": route_id,
            "DepartDate": day,
            "ReturnDate": "",
            "voucher": "",
        },
    )
    adult = None
    adult_classes = {}
    child = None
    senior = None
    vip = None
    for row in data if isinstance(data, list) else []:
        pass_type = row.get("PassTypeId")
        label = str(row.get("PassTypeNm") or "")
        price = row.get("UnitPrice")
        if price is None:
            continue
        if pass_type == 1:
            adult = price
            adult_classes["STANDARD"] = price
        elif pass_type == 4:
            child = price
        elif pass_type == 2:
            senior = price
        elif pass_type == 7:
            vip = price
            adult_classes["VIP"] = price
    return {
        "adult": adult,
        "adult_classes": adult_classes,
        "child": child,
        "senior": senior,
        "vip": vip,
        "currency": "VND",
        "checked_at": day,
        "source_url": SOURCES["superdong"],
    }


def collect_superdong_date_specific(day: str):
    session = superdong_session()
    rows = []
    fare_cache = {}
    for route_id, (origin, destination) in SUPERDONG_ROUTES.items():
        boats = superdong_get_json(
            session,
            "/api/Boat/getBoat",
            {
                "RouteId": route_id,
                "DepartDate": day,
                "NoOfPassenger": 1,
            },
        )
        try:
            fare_cache[route_id] = superdong_fare_for(session, route_id, day)
        except Exception:
            fare_cache[route_id] = None
        for boat in boats if isinstance(boats, list) else []:
            dep = boat.get("DepartTime")
            if not dep:
                continue
            rows.append(
                {
                    "type": "sea",
                    "mode": "FAST FERRY",
                    "operator": "Superdong",
                    "origin": origin,
                    "destination": destination,
                    "departure_time": iso_at(day, dep),
                    "arrival_time": None,
                    "vessel_or_service": boat.get("BoatNm") or "Superdong",
                    "status": "Cập nhật theo ngày",
                    "data_kind": "date_specific_booking",
                    "date_specific": True,
                    "service_date_basis": "date_specific_booking",
                    "source_label": "Nguồn chính thức",
                    "source_url": SOURCES["superdong"],
                    "confidence": "high",
                    "fare": fare_cache.get(route_id),
                }
            )
    session.close()
    return rows


def parsed_day_from_thanh_thoi(strings):
    for s in strings[:80]:
        m = re.search(r"Ngày\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})", s, flags=re.I)
        if m:
            dd, mm, yyyy = map(int, m.groups())
            return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    return None


def parse_thanh_thoi(html: str):
    soup = BeautifulSoup(html, "html.parser")
    strings = list(soup.stripped_strings)
    day = parsed_day_from_thanh_thoi(strings)
    if not day:
        return []
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
                "source_label": "Nguồn chính thức",
                "source_url": SOURCES["thanh_thoi"],
                "confidence": "high" if status else "medium",
                "date_specific": True,
                "service_date_basis": "date_specific",
                "fare": fare_for("Thạnh Thới", origin, destination),
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
            "label": "Thạnh Thới",
            "status": "ok" if tt else "empty",
            "records": len(tt),
            "data_kind": "operational_public",
            "date_specific": True,
            "url": SOURCES["thanh_thoi"],
        }
    except Exception as exc:
        source_state["thanh_thoi"] = {"label": "Thạnh Thới", "status": "error", "records": 0}
        errors.append(f"Thạnh Thới: {exc}")

    try:
        day = now.strftime("%Y-%m-%d")
        pqe = collect_phu_quoc_express(day)
        departures.extend(pqe)
        source_state["phu_quoc_express"] = {
            "label": "Phú Quốc Express",
            "status": "ok" if pqe else "empty",
            "records": len(pqe),
            "data_kind": "date_specific_booking",
            "date_specific": True,
            "url": SOURCES["phu_quoc_express"],
        }
    except Exception as exc:
        source_state["phu_quoc_express"] = {
            "label": "Phú Quốc Express",
            "status": "error",
            "records": 0,
            "date_specific": True,
            "url": SOURCES["phu_quoc_express"],
        }
        errors.append(f"Phú Quốc Express: {exc}")

    try:
        day = now.strftime("%Y-%m-%d")
        sd = collect_superdong_date_specific(day)
        departures.extend(sd)
        source_state["superdong"] = {
            "label": "Superdong",
            "status": "ok" if sd else "empty",
            "records": len(sd),
            "data_kind": "date_specific_booking",
            "date_specific": True,
            "url": SOURCES["superdong"],
        }
    except Exception as exc:
        source_state["superdong"] = {
            "label": "Superdong",
            "status": "error",
            "records": 0,
            "date_specific": True,
            "url": SOURCES["superdong"],
        }
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
    healthy_sources = sum(1 for k in ("thanh_thoi", "phu_quoc_express", "superdong", "bus") if source_state.get(k, {}).get("status") == "ok")

    if healthy_sources == 4:
        health_status = "good"
        network_label = "DATA ONLINE"
        health_desc = "Các nguồn chính đang đọc được. Chuyến theo ngày được tách khỏi lịch tham khảo."
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
                "description": "Thông tin chuyến được cập nhật theo đúng ngày từ các nguồn chính thức."
            },
            "bus": {
                "label": "Có lịch công bố" if bus_ok else "Chưa có dữ liệu",
                "description": "Tuyến VinBus công khai, hiện ở cấp Schedule/Frequency."
            },
            "active_routes": unique_routes(departures, services),
        },
        "sources": {
            "sea": {
                "label": "Nguồn chính thức theo ngày",
                "freshness": "mixed",
            },
            "bus": {
                "label": bus_meta["source"]["label"],
                "freshness": f"verified {bus_meta.get('verified_at')}",
            },
            "registry": source_state,
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
