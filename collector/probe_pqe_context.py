import asyncio, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

TZ=ZoneInfo("Asia/Ho_Chi_Minh")
DAY=datetime.now(TZ).strftime("%Y-%m-%d")
DMY=datetime.now(TZ).strftime("%d/%m/%Y")

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        ctx=await browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        page=await ctx.new_page()

        async def on_request(req):
            if "/Booking/SearchVoyage" in req.url:
                print("REQ_URL", req.url)
                print("REQ_HEADERS", json.dumps(await req.all_headers(), ensure_ascii=False, sort_keys=True))
                print("REQ_COOKIES", json.dumps(await ctx.cookies(), ensure_ascii=False))
                print("LOCAL", await page.evaluate("""() => ({local:{...localStorage},session:{...sessionStorage},cookie:document.cookie})"""))

        async def on_response(resp):
            if "/Booking/SearchVoyage" in resp.url:
                print("RESP_STATUS", resp.status)
                print("RESP_HEADERS", json.dumps(await resp.all_headers(), ensure_ascii=False, sort_keys=True))
                try: print("RESP_BODY", (await resp.text())[:5000])
                except Exception as e: print("RESP_ERR", repr(e))

        page.on("request", on_request)
        page.on("response", on_response)
        await page.goto("https://online.phuquocexpress.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        await page.select_option("#slRoute", "1")
        await page.fill("#dpDepartDate", DMY)
        await page.fill("#NoOfPassenger", "1")
        await page.click("#btnSearch")
        await page.wait_for_timeout(6000)
        print("FINAL_COOKIES", json.dumps(await ctx.cookies(), ensure_ascii=False))
        await browser.close()

asyncio.run(main())
