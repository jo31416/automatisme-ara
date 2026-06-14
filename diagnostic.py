import os
import asyncio
import re
import json
import urllib.request
from playwright.async_api import async_playwright

ARA_USUARI     = os.environ["ARA_USUARI"]
ARA_PASSWORD   = os.environ["ARA_PASSWORD"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def esta_loguejat(page):
    html = await page.content()
    if "inicia-sessio" in html.lower() or "inicia sessió" in html.lower() or "Necessites ajuda per iniciar sessió" in html:
        return False
    return True


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print("Carregant hemeroteca...")
        await page.goto("https://www.ara.cat/hemeroteca/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)

        try:
            await page.click("button:has-text('Acceptar')", timeout=5000)
            await asyncio.sleep(1)
        except:
            pass

        loguejat = await esta_loguejat(page)
        print(f"Sessió iniciada: {loguejat}")

        if not loguejat:
            print("Fent login...")
            await page.goto(
                "https://www.ara.cat/usuari/login?backUrl=https%3A%2F%2Fwww.ara.cat%2Fhemeroteca%2F",
                wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(3)

            try:
                await page.click("button:has-text('Acceptar')", timeout=4000)
                await asyncio.sleep(1)
            except:
                pass

            print("Omplint correu...")
            await page.wait_for_selector("input[type='email'], input[placeholder*='orreu']", timeout=15000)
            await page.fill("input[type='email'], input[placeholder*='orreu']", ARA_USUARI)
            await asyncio.sleep(1)

            print("Clicant 'ACCEDEIX AMB EL CORREU ELECTRÒNIC'...")
            await page.click("button:has-text('ACCEDEIX AMB EL CORREU')", timeout=10000)
            await asyncio.sleep(4)

            print("Omplint contrasenya...")
            await page.wait_for_selector("input[type='password']", timeout=15000)
            await page.fill("input[type='password']", ARA_PASSWORD)
            await asyncio.sleep(1)

            print("Clicant INICIA SESSIÓ...")
            await page.click("button:has-text('INICIA SESSIÓ')", timeout=5000)
            await asyncio.sleep(6)
            print(f"URL després login: {page.url}")

            if "login" in page.url:
                raise Exception("El login no ha funcionat.")

        cookies = await context.cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "ara.cat" in c.get("domain", "")])
        print(f"Cookies: {len([c for c in cookies if 'ara.cat' in c.get('domain','')])} cookies d'ara.cat")

        def api_get_text(url):
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Cookie": cookie_header,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Referer": "https://www.ara.cat/hemeroteca/",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")

        print("Obtenint publicacions...")
        body = api_get_text("https://www.ara.cat/api/front/archive/publications?limit=5")
        data_json = json.loads(body)
        for item in data_json["response"]["items"]:
            item_copy = {k: v for k, v in item.items() if k != "image"}
            print(json.dumps(item_copy, indent=2, ensure_ascii=False))
            print("---")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
