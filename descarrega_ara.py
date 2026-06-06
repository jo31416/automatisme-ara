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


async def descarrega_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # 1. LOGIN
        print("Carregant pàgina de login...")
        await page.goto("https://perfil.ara.cat/login", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(4)

        # Acceptar cookies
        try:
            await page.click("button:has-text('Acceptar')", timeout=5000)
            await asyncio.sleep(1)
        except:
            pass

        # Diagnòstic: llistar iframes
        frames = page.frames
        print(f"Frames trobats: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: url={frame.url}")
            inputs = await frame.query_selector_all("input")
            print(f"    Inputs: {len(inputs)}")
            for inp in inputs:
                t = await inp.get_attribute("type") or ""
                n = await inp.get_attribute("name") or ""
                i2 = await inp.get_attribute("id") or ""
                pl = await inp.get_attribute("placeholder") or ""
                print(f"      input type='{t}' name='{n}' id='{i2}' placeholder='{pl}'")

        # Buscar el frame que té inputs
        login_frame = None
        for frame in frames:
            inputs = await frame.query_selector_all("input")
            if len(inputs) >= 2:
                login_frame = frame
                print(f"Frame amb inputs trobat: {frame.url}")
                break

        if login_frame is None:
            print("No s'ha trobat cap frame amb inputs, usant pàgina principal")
            login_frame = page

        # Omplir formulari
        print("Omplint formulari de login...")
        inputs = await login_frame.query_selector_all("input")
        await inputs[0].fill(ARA_USUARI)
        await inputs[1].fill(ARA_PASSWORD)

        # Clicar submit
        await login_frame.query_selector("button[type='submit']")
        buttons = await login_frame.query_selector_all("button")
        for btn in buttons:
            t = await btn.get_attribute("type") or ""
            txt = (await btn.inner_text()).strip()
            print(f"  Botó: type='{t}' text='{txt}'")
            if t == "submit" or any(x in txt.lower() for x in ["entra", "accede", "login", "iniciar"]):
                await btn.click()
                break

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
