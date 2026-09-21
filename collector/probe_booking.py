# One-time network probe for date-specific public booking search.\nfrom __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TODAY_ISO = datetime.now(TZ).strftime("%Y-%m-%d")
TODAY_DMY = datetime.now(TZ).strftime("%d/%m/%Y")

TARGETS = [
    {
        "name": "PhuQuocExpress",
        "url": "https://online.phuquocexpress.com/",
        "origin": "Rạch Giá",
        "destination": "Phú Quốc",
    },
    {
        "name": "Superdong",
        "url": "https://online.superdong.com.vn/Booking",
        "origin": "Rạch Giá",
        "destination": "Phú Quốc",
    },
]


def fold(value: str) -> str:
    s = unicodedata.normalize("NFD", value or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def compact(value, limit=1200):
    if value is None:
        return None
    text = str(value).replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


async def inspect_controls(page, label):
    data = await page.evaluate(
        """() => ({
          forms: Array.from(document.forms).map((f,i)=>({i,action:f.action,method:f.method,id:f.id,name:f.name})),
          selects: Array.from(document.querySelectorAll('select')).map((s,i)=>({
            i,id:s.id,name:s.name,visible:!!(s.offsetWidth||s.offsetHeight||s.getClientRects().length),
            options:Array.from(s.options).map(o=>({value:o.value,text:(o.textContent||'').trim()})).slice(0,80)
          })),
          inputs: Array.from(document.querySelectorAll('input')).map((x,i)=>({
            i,id:x.id,name:x.name,type:x.type,placeholder:x.placeholder,value:x.value,
            visible:!!(x.offsetWidth||x.offsetHeight||x.getClientRects().length)
          })).slice(0,120),
          buttons: Array.from(document.querySelectorAll('button,input[type=button],input[type=submit]')).map((b,i)=>({
            i,id:b.id,name:b.name,type:b.type,text:(b.textContent||b.value||'').trim(),
            visible:!!(b.offsetWidth||b.offsetHeight||b.getClientRects().length)
          })).slice(0,80),
          scripts: Array.from(document.scripts).map(s=>s.src).filter(Boolean)
        })"""
    )
    print(f"CONTROL_DUMP {label} {json.dumps(data, ensure_ascii=False)}")



async def inspect_booking_bundle(page, label):
    scripts = await page.locator("script[src*='BookingJs']").evaluate_all("els => els.map(x => x.src)")
    for src in scripts:
        try:
            text_body = await page.evaluate("""async (url) => await (await fetch(url)).text()""", src)
        except Exception as exc:
            print(f"BUNDLE_ERROR {label} {src} {compact(exc)}")
            continue
        print(f"BUNDLE_SRC {label} {src}")
        patterns = [
            r"""["']([^"'\n]*(?:/api/|/Booking/|/Home/|DataSource/)[^"'\n]*)["']""",
            r"""\b(?:Get|Search|Load|Find)[A-Za-z0-9_]{3,}\b""",
        ]
        hits = []
        for pattern in patterns:
            hits.extend(re.findall(pattern, text_body, flags=re.I))
        unique = []
        for hit in hits:
            value = hit if isinstance(hit, str) else " ".join(hit)
            if value and value not in unique:
                unique.append(value)
        print(f"BUNDLE_ENDPOINTS {label} {json.dumps(unique[:180], ensure_ascii=False)}")
        for needle in ["slRoute", "btnSearchBoat", "SearchVoyage", "ScheduleBoat", "GetRoute", "getFare", "routeApi.getFare", "getBoat", "RouteId", "dpDepartDate"]:
            pos = text_body.find(needle)
            if pos >= 0:
                print(f"BUNDLE_SNIP {label} {needle} {compact(text_body[max(0,pos-900):pos+2200], 3200)}")
        for needle in ["routeApi.getRoute", "api/Route/GetRoute", "$.get(routeApi.getRoute", "$.post(routeApi.getRoute"]:
            positions = [m.start() for m in re.finditer(re.escape(needle), text_body)]
            for idx, pos in enumerate(positions[:8]):
                print(f"BUNDLE_OCCURRENCE {label} {needle} {idx} {compact(text_body[max(0,pos-1200):pos+2600], 3900)}")


async def choose_route(page, origin, destination):
    selects = page.locator("select:visible")
    n = await selects.count()
    wanted_a = fold(origin)
    wanted_b = fold(destination)
    for i in range(n):
        sel = selects.nth(i)
        opts = await sel.locator("option").all_text_contents()
        for idx, text in enumerate(opts):
            f = fold(text)
            if wanted_a in f and wanted_b in f:
                try:
                    await sel.select_option(index=idx)
                    print(f"SELECTED_ROUTE select={i} option={idx} text={compact(text)}")
                    return True
                except Exception as exc:
                    print(f"SELECT_ROUTE_ERROR select={i} option={idx} err={compact(exc)}")
    print("SELECTED_ROUTE none")
    return False


async def set_date(page):
    candidates = [
        "input[type=date]:visible",
        "input[name*=Date i]:visible",
        "input[id*=Date i]:visible",
        "input[name*=Ngay i]:visible",
        "input[id*=Ngay i]:visible",
    ]
    seen = set()
    for selector in candidates:
        loc = page.locator(selector)
        for i in range(await loc.count()):
            el = loc.nth(i)
            key = await el.get_attribute("id") or await el.get_attribute("name") or f"{selector}:{i}"
            if key in seen:
                continue
            seen.add(key)
            typ = (await el.get_attribute("type") or "").lower()
            for value in ([TODAY_ISO] if typ == "date" else [TODAY_DMY, TODAY_ISO]):
                try:
                    await el.fill(value)
                    await el.dispatch_event("change")
                    print(f"SET_DATE key={key} type={typ} value={value}")
                    return True
                except Exception:
                    try:
                        await el.evaluate(
                            "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}",
                            value,
                        )
                        print(f"SET_DATE_JS key={key} type={typ} value={value}")
                        return True
                    except Exception:
                        pass
    print("SET_DATE none")
    return False


async def set_passenger(page):
    inputs = page.locator("input:visible")
    for i in range(await inputs.count()):
        el = inputs.nth(i)
        name = fold((await el.get_attribute("name") or "") + " " + (await el.get_attribute("id") or "") + " " + (await el.get_attribute("placeholder") or ""))
        typ = (await el.get_attribute("type") or "").lower()
        if typ in {"number","text"} and any(k in name for k in ["passenger","quantity","amount","soluong","so luong","person"]):
            try:
                await el.fill("1")
                await el.dispatch_event("change")
                print(f"SET_PASSENGER i={i} name={compact(name)}")
                return True
            except Exception:
                pass
    return False


async def click_search(page):
    candidates = [
        page.get_by_role("button", name=re.compile(r"tìm kiếm|tìm tàu|search", re.I)),
        page.locator("button:visible").filter(has_text=re.compile(r"tìm kiếm|tìm tàu|search", re.I)),
        page.locator("input[type=submit]:visible"),
        page.locator("input[type=button]:visible"),
    ]
    for loc in candidates:
        try:
            if await loc.count():
                target = loc.first
                text = await target.text_content() or await target.get_attribute("value") or ""
                if loc != candidates[2] and loc != candidates[3] or re.search(r"tìm|search", text, re.I):
                    await target.click()
                    print(f"CLICK_SEARCH text={compact(text)}")
                    return True
        except Exception:
            continue
    print("CLICK_SEARCH none")
    return False


async def dump_results(page, label):
    print(f"RESULT_URL {label} {page.url}")
    tables = page.locator("table:visible")
    for i in range(min(await tables.count(), 12)):
        try:
            txt = compact(await tables.nth(i).inner_text(), 3500)
            if txt:
                print(f"TABLE_TEXT {label} {i} {txt}")
        except Exception:
            pass
    body = compact(await page.locator("body").inner_text(), 7000)
    print(f"BODY_TEXT {label} {body}")



async def probe_superdong_api(page):
    try:
        globals_data = await page.evaluate("""() => ({SiteRoot: window.SiteRoot, routeApi: window.routeApi, boatApi: window.boatApi})""")
        print("SUPERDONG_GLOBALS "+json.dumps(globals_data, ensure_ascii=False))
        route_url = (globals_data.get("routeApi") or {}).get("getRoute") or ((globals_data.get("SiteRoot") or "/") + "api/Route/GetRoute")
        route_data = await page.evaluate("""async (url) => {
          const r = await fetch(url);
          return {url,status:r.status, text:await r.text()};
        }""", route_url)
        print("SUPERDONG_ROUTE_API "+json.dumps(route_data, ensure_ascii=False))
        parsed = json.loads(route_data.get("text") or "[]")
        route = None
        for item in parsed if isinstance(parsed, list) else []:
            blob = fold(json.dumps(item, ensure_ascii=False))
            if "rach gia" in blob and "phu quoc" in blob:
                route = item
                break
        if route:
            rid = route.get("RouteId") or route.get("Id") or route.get("Value") or route.get("id")
            print("SUPERDONG_ROUTE_PICK "+json.dumps(route, ensure_ascii=False))
            if rid is not None:
                boat_base = (globals_data.get("boatApi") or {}).get("getBoat") or ((globals_data.get("SiteRoot") or "/") + "api/Boat/getBoat")
                boat = await page.evaluate("""async ([base,rid,day]) => {
                  const u=base+'?RouteId='+encodeURIComponent(rid)+'&DepartDate='+encodeURIComponent(day)+'&NoOfPassenger=1';
                  const r=await fetch(u); return {url:u,status:r.status,text:await r.text()};
                }""", [boat_base, rid, TODAY_ISO])
                print("SUPERDONG_BOAT_API "+json.dumps(boat, ensure_ascii=False))
    except Exception as exc:
        print("SUPERDONG_API_ERROR "+compact(repr(exc), 3000))


async def run_target(browser, target):
    context = await browser.new_context(
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    )
    page = await context.new_page()
    captured = []

    def on_request(req):
        if req.resource_type in {"xhr", "fetch"}:
            captured.append({
                "kind": "request",
                "method": req.method,
                "url": req.url,
                "post_data": compact(req.post_data, 1800),
                "resource_type": req.resource_type,
            })

    async def on_response(resp):
        req = resp.request
        if req.resource_type not in {"xhr", "fetch"}:
            return
        item = {
            "kind": "response",
            "status": resp.status,
            "url": resp.url,
            "method": req.method,
            "content_type": resp.headers.get("content-type", ""),
        }
        try:
            ct = item["content_type"].lower()
            if "json" in ct or "text" in ct or "html" in ct:
                item["body"] = compact(await resp.text(), 2800)
        except Exception:
            pass
        captured.append(item)

    page.on("request", on_request)
    page.on("response", on_response)

    name = target["name"]
    print(f"PROBE_START {name} {target['url']}")
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        await inspect_controls(page, name)
        await inspect_booking_bundle(page, name)
        if name == "Superdong":
            await probe_superdong_api(page)
        await choose_route(page, target["origin"], target["destination"])
        await set_date(page)
        await set_passenger(page)
        await page.wait_for_timeout(500)
        await click_search(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(2500)
        await dump_results(page, name)
    except Exception as exc:
        print(f"PROBE_ERROR {name} {compact(repr(exc), 2500)}")
    finally:
        for item in captured:
            print(f"NETWORK {name} {json.dumps(item, ensure_ascii=False)}")
        await context.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for target in TARGETS:
            await run_target(browser, target)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
