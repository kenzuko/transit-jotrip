from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://www.binhanhatien.vn"
URLS = [BASE + "/", BASE + "/dat-ve"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

KEYWORDS = re.compile(r"(ajax|fetch\(|axios|\.get\(|\.post\(|url\s*:|schedule|price|fare|route|booking|dat-ve|search|voyage|ticket|gia|lịch|lich|chuyến|chuyen)", re.I)
PATHS = re.compile(r"""(?:"|')((?:https?:)?//[^"'\s]+|/[A-Za-z0-9_./?=&%-]+)(?:"|')""")

def dump_forms(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for idx, form in enumerate(soup.find_all("form"), 1):
        print(f"FORM {idx}: method={form.get('method')} action={form.get('action')} id={form.get('id')} class={form.get('class')}")
        for el in form.find_all(["input", "select", "button"]):
            print(" ", el.name, "name=", el.get("name"), "id=", el.get("id"), "type=", el.get("type"), "value=", el.get("value"))
            if el.name == "select":
                for opt in el.find_all("option")[:40]:
                    print("   OPTION", repr(opt.get_text(" ", strip=True)), "value=", repr(opt.get("value")))
    return soup

def inspect_scripts(s: requests.Session, page_url: str, soup: BeautifulSoup):
    scripts = []
    for sc in soup.find_all("script"):
        src = sc.get("src")
        if src:
            full = urljoin(page_url, src)
            scripts.append(full)
            print("SCRIPT_SRC", full)
        else:
            txt = sc.get_text("\n", strip=False)
            if KEYWORDS.search(txt or ""):
                print("INLINE_JS_BEGIN")
                print((txt or "")[:12000])
                print("INLINE_JS_END")

    for js_url in scripts:
        host = urlparse(js_url).hostname or ""
        if host not in {urlparse(page_url).hostname, "binhanhatien.vn", "www.binhanhatien.vn"}:
            continue
        try:
            h = {
                "Accept": "application/javascript,text/javascript,*/*;q=0.1",
                "Referer": page_url,
                "Sec-Fetch-Dest": "script",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "same-origin",
            }
            jr = s.get(js_url, headers=h, timeout=20)
            ctype = jr.headers.get("content-type", "")
            print("\nJS", js_url, "status", jr.status_code, "ctype", ctype, "len", len(jr.text))
            txt = jr.text
            print("JS_HEAD", repr(txt[:300]))
            if KEYWORDS.search(txt):
                for line in txt.splitlines():
                    if KEYWORDS.search(line):
                        print("MATCH", line[:2000])
                found = []
                for m in PATHS.finditer(txt):
                    p = m.group(1)
                    if any(k in p.lower() for k in ["api", "book", "dat-ve", "schedule", "price", "fare", "route", "ticket", "search", "trip"]):
                        if p not in found:
                            found.append(p)
                for p in found[:300]:
                    print("PATH", p)
        except Exception as exc:
            print("JS_ERROR", js_url, repr(exc))

def inspect_booking_post(s: requests.Session):
    payload = {
        "idLog": "1914",
        "booking_type": "1",
        "PFrom": "77",
        "DFrom": "22/09/2026",
        "DBack": "",
        "Adults": "1",
        "Elderlys": "0",
        "Children": "0",
        "Humans": "0",
        "Motorbikes": "0",
        "Cars": "0",
    }
    print("\n=== POST /booking route 77 22/09/2026 ===")
    r = s.post(
        BASE + "/booking",
        data=payload,
        headers={"Referer": BASE + "/dat-ve", "Origin": BASE},
        timeout=25,
        allow_redirects=True,
    )
    print("status", r.status_code, "final", r.url, "history", [(x.status_code, x.headers.get("location")) for x in r.history], "len", len(r.text))
    print("ctype", r.headers.get("content-type"))
    soup = dump_forms(r.text)

    text = "\n".join(soup.stripped_strings)
    for line in text.splitlines():
        if re.search(r"(Hà Tiên|Phú Quốc|22/09/2026|22-09-2026|\b\d{1,2}:\d{2}\b|giá|vé|chuyến|lịch)", line, re.I):
            print("BOOKING_TEXT", line[:1000])

    for sc in soup.find_all("script"):
        txt = sc.get_text("\n", strip=False)
        if KEYWORDS.search(txt or ""):
            print("BOOKING_INLINE_JS_BEGIN")
            print((txt or "")[:15000])
            print("BOOKING_INLINE_JS_END")

def main():
    s = requests.Session()
    s.headers.update(HEADERS)

    for url in URLS:
        print("\n=== PAGE", url, "===")
        r = s.get(url, timeout=25)
        print("status", r.status_code, "final", r.url, "len", len(r.text))
        print("server", r.headers.get("server"))
        print("set-cookie", r.headers.get("set-cookie"))
        soup = dump_forms(r.text)
        inspect_scripts(s, r.url, soup)

    inspect_booking_post(s)

if __name__ == "__main__":
    main()
