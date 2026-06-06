import os
import asyncio
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from playwright.async_api import async_playwright

# Les credencials vénen de les variables d'entorn (GitHub Secrets)
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
        print("Fent login a l'Ara...")
        await page.goto("https://perfil.ara.cat/login", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        # Acceptar cookies si apareix el banner
        try:
            await page.click("button:has-text('Acceptar')", timeout=5000)
            print("Cookies acceptades")
        except:
            pass

        # Omplir formulari de login
        await page.fill("input[type='email'], input[name='email'], input[id='email']", ARA_USUARI)
        await page.fill("input[type='password'], input[name='password'], input[id='password']", ARA_PASSWORD)
        await page.click("button[type='submit'], input[type='submit'], button:has-text('Entra')")
        await asyncio.sleep(3)
        print(f"Pàgina actual després del login: {page.url}")

        # 2. ANAR A L'HEMEROTECA
        print("Anant a l'hemeroteca...")
        await page.goto("https://www.ara.cat/hemeroteca/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)

        # Captura screenshot per diagnòstic
        await page.screenshot(path="/tmp/hemeroteca.png")

        # 3. BUSCAR L'ENLLAÇ AL PDF
        links = await page.query_selector_all("a")
        print(f"Total d'enllaços: {len(links)}")
        pdf_url = None
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()[:60]
            if href:
                print(f"  [{text}] -> {href}")
            if "pdf" in href.lower():
                pdf_url = href if href.startswith("http") else "https://www.ara.cat" + href
                break

        if not pdf_url:
            # Intenta descàrrega via clic en botó PDF
            print("Intentant descàrrega via clic...")
            try:
                async with page.expect_download(timeout=30000) as dl:
                    await page.click("text=PDF", timeout=10000)
                download = await dl.value
                fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
                await download.save_as(fitxer_pdf)
                await browser.close()
                return fitxer_pdf
            except Exception as e:
                print(f"Error clic PDF: {e}")
                raise Exception("No s'ha trobat l'enllaç al PDF. Revisa els logs.")

        print(f"URL del PDF: {pdf_url}")
        async with page.expect_download(timeout=60000) as dl:
            await page.goto(pdf_url)
        download = await dl.value
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
        await download.save_as(fitxer_pdf)

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


