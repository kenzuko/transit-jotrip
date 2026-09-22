from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

URLS = [
    "https://www.binhanhatien.vn/",
    "https://www.binhanhatien.vn/dat-ve",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JoTrip-Transit-Diagnostic/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

KEYWORDS = re.compile(r"(ajax|fetch\(|axios|\.get\(|\.post\(|url\s*:|schedule|price|fare|route|booking|dat-ve|search|voyage|ticket)", re.I)
PATHS = re.compile(r"""(?:"|')((?:https?:)?//[^"'\s]+|/[A-Za-z0-9_./?-]+)(?:"|')""")

def main():
    s = requests.Session()
    s.headers.update(HEADERS)

    for url in URLS:
        print("\n=== PAGE", url, "===")
        r = s.get(url, timeout=25)
        print("status", r.status_code, "final", r.url, "len", len(r.text))
        print("server", r.headers.get("server"))
        print("set-cookie", r.headers.get("set-cookie"))

        soup = BeautifulSoup(r.text, "html.parser")

        for idx, form in enumerate(soup.find_all("form"), 1):
            print(f"FORM {idx}: method={form.get('method')} action={form.get('action')} id={form.get('id')} class={form.get('class')}")
            for el in form.find_all(["input", "select", "button"]):
                print(" ", el.name, "name=", el.get("name"), "id=", el.get("id"), "type=", el.get("type"), "value=", el.get("value"))
                if el.name == "select":
                    for opt in el.find_all("option")[:30]:
                        print("   OPTION", repr(opt.get_text(" ", strip=True)), "value=", repr(opt.get("value")))

        scripts = []
        for sc in soup.find_all("script"):
            src = sc.get("src")
            if src:
                full = urljoin(r.url, src)
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
            if host not in {urlparse(r.url).hostname, "binhanhatien.vn", "www.binhanhatien.vn"}:
                continue
            try:
                jr = s.get(js_url, timeout=20)
                ctype = jr.headers.get("content-type", "")
                print("\nJS", js_url, "status", jr.status_code, "ctype", ctype, "len", len(jr.text))
                txt = jr.text
                if KEYWORDS.search(txt):
                    for line in txt.splitlines():
                        if KEYWORDS.search(line):
                            print("MATCH", line[:1500])
                    found = []
                    for m in PATHS.finditer(txt):
                        p = m.group(1)
                        if any(k in p.lower() for k in ["api", "book", "dat-ve", "schedule", "price", "fare", "route", "ticket", "search"]):
                            if p not in found:
                                found.append(p)
                    for p in found[:200]:
                        print("PATH", p)
            except Exception as exc:
                print("JS_ERROR", js_url, repr(exc))

if __name__ == "__main__":
    main()
