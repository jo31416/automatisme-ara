import os
import asyncio
import smtplib
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


async def descarrega_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # 1. LOGIN
        print("Carregant pàgina de login...")
        await page.goto("https://perfil.ara.cat/login", timeout=60000)

        # Acceptar cookies
        try:
            await page.wait_for_selector("button:has-text('Acceptar')", timeout=8000)
            await page.click("button:has-text('Acceptar')")
            await asyncio.sleep(1)
        except:
            pass

        # Esperar que aparegui algun input (fins a 30 segons)
        print("Esperant que carregui el formulari...")
        try:
            await page.wait_for_selector("input", timeout=30000)
        except:
            print("Timeout esperant inputs — fent screenshot")
            await page.screenshot(path="/tmp/login_page.png")
            # Mostrar el HTML per diagnòstic
            html = await page.content()
            print("HTML (primers 3000 chars):")
            print(html[:3000])
            raise Exception("El formulari de login no ha carregat.")

        # Diagnòstic
        inputs = await page.query_selector_all("input")
        print(f"Inputs trobats: {len(inputs)}")
        for inp in inputs:
            t = await inp.get_attribute("type") or ""
            n = await inp.get_attribute("name") or ""
            i = await inp.get_attribute("id") or ""
            pl = await inp.get_attribute("placeholder") or ""
            print(f"  input type='{t}' name='{n}' id='{i}' placeholder='{pl}'")

        # Omplir formulari
        print("Omplint formulari...")
        await inputs[0].fill(ARA_USUARI)
        await inputs[1].fill(ARA_PASSWORD)

        buttons = await page.query_selector_all("button")
        clicked = False
        for btn in buttons:
            t = await btn.get_attribute("type") or ""
            txt = (await btn.inner_text()).strip()
            print(f"  Botó: type='{t}' text='{txt}'")
            if t == "submit" or any(x in txt.lower() for x in ["entra", "accede", "login", "iniciar", "accedir"]):
                await btn.click()
                clicked = True
                break
        if not clicked and buttons:
            await buttons[-1].click()

        await asyncio.sleep(4)
        print(f"URL després del login: {page.url}")

        # 2. ANAR A L'HEMEROTECA
        print("Anant a l'hemeroteca...")
        await page.goto("https://www.ara.cat/hemeroteca/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)

        # 3. BUSCAR L'ENLLAÇ AL PDF
        links = await page.query_selector_all("a")
        print(f"Total d'enllaços: {len(links)}")
        pdf_url = None
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()[:60]
            if any(x in href.lower() for x in ["pdf", "paper", "download"]):
                print(f"  [CANDIDAT] [{text}] -> {href}")
            if "pdf" in href.lower() and not pdf_url:
                pdf_url = href if href.startswith("http") else "https://www.ara.cat" + href

        if not pdf_url:
            await page.screenshot(path="/tmp/hemeroteca.png")
            html = await page.content()
            print("HTML hemeroteca (primers 2000 chars):")
            print(html[:2000])
            raise Exception("No s'ha trobat cap URL de PDF.")

        print(f"URL del PDF: {pdf_url}")
        import urllib.request
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
        urllib.request.urlretrieve(pdf_url, fitxer_pdf)

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
