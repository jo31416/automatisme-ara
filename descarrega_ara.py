import os
import asyncio
import smtplib
import re
import json
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

        # 3. OBTENIR LES COOKIES DE SESSIÓ
        cookies = await context.cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "ara.cat" in c.get("domain", "")])
        print(f"Cookies obtingudes: {len([c for c in cookies if 'ara.cat' in c.get('domain','')])} cookies d'ara.cat")

        # 4. CRIDAR LES APIs DES DE PYTHON amb les cookies
        import urllib.request
        import urllib.error

        def api_get(url):
            import gzip, zlib
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Cookie": cookie_header,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Referer": "https://www.ara.cat/hemeroteca/",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                encoding = resp.info().get("Content-Encoding", "")
                if encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif encoding == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except:
                        raw = zlib.decompress(raw, -15)
                return raw.decode("utf-8", errors="replace")

        # Obtenir l'ID de la publicació més recent
        print("Obtenint ID de la publicació...")
        body = api_get("https://www.ara.cat/api/front/archive/publications?limit=1")
        print(f"Resposta publications: {body[:300]}")

        pub_ids = re.findall(r'"id"\s*:\s*(\d+)', body)
        if not pub_ids:
            raise Exception("No s'ha trobat l'ID de publicació.")
        pub_id = pub_ids[0]
        print(f"ID de publicació: {pub_id}")

        # 5. OBTENIR L'URL SIGNADA DEL PDF
        print(f"Obtenint URL del PDF...")
        body2 = api_get(f"https://www.ara.cat/api/front/archive/publication/{pub_id}")
        print(f"Resposta publication: {body2[:500]}")

        match = re.search(r'https://aranx-data[^"\'<>\s\\]+\.pdf[^"\'<>\s\\]*', body2)
        if not match:
            match = re.search(r'https://[^"\'<>\s\\]*amazonaws[^"\'<>\s\\]*\.pdf[^"\'<>\s\\]*', body2)
        if not match:
            raise Exception(f"No s'ha trobat l'URL del PDF. Body: {body2[:500]}")

        pdf_url = match.group(0).replace("\\/", "/")
        print(f"URL del PDF: {pdf_url[:80]}...")

        # 6. DESCARREGAR EL PDF
        avui = date.today()
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{avui}.pdf")
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(fitxer_pdf, "wb") as f:
                f.write(response.read())

        await browser.close()
        mida = os.path.getsize(fitxer_pdf)
        print(f"PDF desat: {fitxer_pdf} ({mida:,} bytes)")
        return fitxer_pdf


def envia_email(fitxer_pdf):
    avui = date.today().strftime("%d/%m/%Y")
    assumpte = f"Diari Ara — {avui}"
    cos = f"Bon dia,\n\nAdjunt trobaràs l'edició del diari Ara del {avui}.\n\nBona lectura!"

    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USUARI
    msg["To"]      = ", ".join(DESTINATARIS)
    msg["Subject"] = assumpte
    msg.attach(MIMEText(cos, "plain", "utf-8"))

    with open(fitxer_pdf, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    nom_fitxer = os.path.basename(fitxer_pdf)
    part.add_header("Content-Disposition", f'attachment; filename="{nom_fitxer}"')
    msg.attach(part)

    print("Enviant email...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(GMAIL_USUARI, GMAIL_PASSWORD)
        servidor.sendmail(GMAIL_USUARI, DESTINATARIS, msg.as_string())
    print(f"Email enviat a: {', '.join(DESTINATARIS)}")


if __name__ == "__main__":
    async def main():
        pdf = await descarrega_pdf()
        envia_email(pdf)
        print("✓ Tot completat correctament.")

    try:
        asyncio.run(main())
    except Exception as e:
        print(f"✗ Error: {e}")
        raise
