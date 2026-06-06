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

            # PAS 1: correu
            print("Omplint correu...")
            await page.wait_for_selector("input[type='email'], input[placeholder*='orreu']", timeout=15000)
            await page.fill("input[type='email'], input[placeholder*='orreu']", ARA_USUARI)
            await asyncio.sleep(1)

            print("Clicant 'ACCEDEIX AMB EL CORREU ELECTRÒNIC'...")
            await page.click("button:has-text('ACCEDEIX AMB EL CORREU')", timeout=10000)
            await asyncio.sleep(4)
            print(f"URL pas 1: {page.url}")

            # PAS 2: contrasenya — diagnòstic de botons
            print("Esperant camp de contrasenya...")
            await page.wait_for_selector("input[type='password']", timeout=15000)
            await page.fill("input[type='password']", ARA_PASSWORD)
            await asyncio.sleep(1)

            # Llistar tots els botons per saber quin clicar
            buttons = await page.query_selector_all("button")
            print(f"Botons trobats: {len(buttons)}")
            for btn in buttons:
                t = await btn.get_attribute("type") or ""
                txt = (await btn.inner_text()).strip()
                print(f"  button type='{t}' text='{txt}'")

            # Clicar el primer botó submit, o l'últim botó si no n'hi ha
            clicked = False
            for btn in buttons:
                t = await btn.get_attribute("type") or ""
                txt = (await btn.inner_text()).strip().upper()
                if t == "submit" or any(x in txt for x in ["ENTRA", "ACCEDEIX", "CONTINUA", "LOGIN", "INICIAR"]):
                    await btn.click()
                    print(f"Clicat botó: '{txt}'")
                    clicked = True
                    break
            if not clicked:
                print("Cap botó submit trobat, fent Enter...")
                await page.keyboard.press("Enter")

            await asyncio.sleep(6)
            print(f"URL després login: {page.url}")

            # Verificar si el login ha anat bé
            if "login" in page.url:
                html = await page.content()
                errors = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)<', html)
                print(f"Errors de login detectats: {errors}")
                raise Exception("El login no ha funcionat, seguim a la pàgina de login.")

            # Anar a l'hemeroteca
            print("Anant a l'hemeroteca...")
            await page.goto("https://www.ara.cat/hemeroteca/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)

        # 3. BUSCAR EL PDF
        print(f"URL hemeroteca: {page.url}")
        html = await page.content()

        pdf_urls = re.findall(r'https?://[^\s"\'<>]*\.pdf[^\s"\'<>]*', html, re.IGNORECASE)
        print(f"PDFs al HTML: {pdf_urls}")

        if pdf_urls:
            pdf_url = pdf_urls[0]
        else:
            links = await page.query_selector_all("a")
            print(f"Total enllaços: {len(links)}")
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()[:60]
                if href and href != "#":
                    print(f"  [{text[:40]}] -> {href}")
            raise Exception("No s'ha trobat el PDF.")

        # 4. DESCARREGAR
        print(f"Descarregant: {pdf_url}")
        import urllib.request
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req) as response:
            with open(fitxer_pdf, "wb") as f:
                f.write(response.read())

        await browser.close()
        print(f"PDF desat a: {fitxer_pdf}")
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
