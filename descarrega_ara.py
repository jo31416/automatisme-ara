import os
import asyncio
import smtplib
import re
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from playwright.async_api import async_playwright

GMAIL_USUARI   = os.environ["GMAIL_USUARI"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
DESTINATARIS   = os.environ["DESTINATARIS"].split(",")
ARA_USUARI     = os.environ["ARA_USUARI"]
ARA_PASSWORD   = os.environ["ARA_PASSWORD"]
CARPETA_DESAR  = "/tmp"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def esta_loguejat(page):
    html = await page.content()
    if "inicia-sessio" in html.lower() or "inicia sessió" in html.lower() or "Necessites ajuda per iniciar sessió" in html:
        return False
    return True


async def descarrega_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # 1. COMPROVAR SESSIÓ
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

        # 2. LOGIN SI CAL
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

            print("Anant a l'hemeroteca...")
            await page.goto("https://www.ara.cat/hemeroteca/", wait_until="domcontentloaded", timeout=60000)

        # Esperar contingut dinàmic
        print("Esperant contingut dinàmic (15s)...")
        await asyncio.sleep(15)

        # DIAGNÒSTIC: Guardar el HTML complet
        html = await page.content()
        with open("/tmp/hemeroteca_full.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML complet desat ({len(html)} chars)")

        # Buscar totes les URLs que continguin "static" o "ara.cat" al HTML
        all_urls = re.findall(r'https?://[^\s"\'<>]+', html)
        ara_urls = [u for u in all_urls if "static" in u and "ara.cat" in u]
        print(f"\nURLs de static.ara.cat al HTML ({len(ara_urls)}):")
        for u in set(ara_urls):
            print(f"  {u}")

        # Buscar tots els atributs href i onclick
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
        print(f"\nTots els hrefs ({len(hrefs)}):")
        for h in hrefs:
            if h != "#" and "javascript" not in h and len(h) > 5:
                print(f"  {h}")

        # Buscar onclick que puguin contenir URLs
        onclicks = re.findall(r'onclick=["\']([^"\']+)["\']', html)
        print(f"\nOnclicks: {onclicks[:20]}")

        # Buscar data-attributes
        data_attrs = re.findall(r'data-[a-z-]+=["\']([^"\']*(?:pdf|download|paper)[^"\']*)["\']', html, re.IGNORECASE)
        print(f"\nData attrs amb pdf/download/paper: {data_attrs}")

        raise Exception("Mode diagnòstic — revisa els logs per trobar l'URL del PDF")


if __name__ == "__main__":
    async def main():
        await descarrega_pdf()

    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Info: {e}")
