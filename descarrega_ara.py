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
        login_url = "https://www.ara.cat/usuari/login?backUrl=https%3A%2F%2Fwww.ara.cat%2Fhemeroteca%2F"
        print(f"Carregant login: {login_url}")
        await page.goto(login_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        # Acceptar cookies si apareix
        try:
            await page.click("button:has-text('Acceptar')", timeout=5000)
            await asyncio.sleep(1)
        except:
            pass

        print(f"URL actual: {page.url}")

        # Comprovar si ja estem logats (redirigit directament a l'hemeroteca)
        if "hemeroteca" in page.url:
            print("Ja estem logats, redirigit a l'hemeroteca!")
        else:
            # PAS 1: omplir el correu i clicar "ACCEDEIX AMB EL CORREU ELECTRÒNIC"
            print("Omplint correu electrònic...")
            await page.wait_for_selector("input[type='email'], input[placeholder*='orreu']", timeout=15000)
            await page.fill("input[type='email'], input[placeholder*='orreu']", ARA_USUARI)
            await asyncio.sleep(1)

            print("Clicant 'ACCEDEIX AMB EL CORREU ELECTRÒNIC'...")
            await page.click("button:has-text('ACCEDEIX AMB EL CORREU')", timeout=10000)
            await asyncio.sleep(3)
            print(f"URL després del pas 1: {page.url}")

            # PAS 2: introduir la contrasenya
            print("Omplint contrasenya...")
            await page.wait_for_selector("input[type='password']", timeout=15000)
            await page.fill("input[type='password']", ARA_PASSWORD)
            await asyncio.sleep(1)

            # Clicar submit
            for selector in ["button[type='submit']", "button:has-text('ENTRA')", "button:has-text('Accedeix')", "button:has-text('CONTINUA')"]:
                try:
                    await page.click(selector, timeout=3000)
                    print(f"Clicat: {selector}")
                    break
                except:
                    pass

            await asyncio.sleep(5)
            print(f"URL després del login: {page.url}")

        # 2. ANAR A L'HEMEROTECA
        if "hemeroteca" not in page.url:
            print("Anant a l'hemeroteca...")
            await page.goto("https://www.ara.cat/hemeroteca/", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)

        print(f"URL hemeroteca: {page.url}")

        # 3. BUSCAR L'ENLLAÇ AL PDF
        # Buscar a tots els atributs (href, onclick, data-*)
        import re
        html = await page.content()
        pdf_mentions = re.findall(r'https?://[^\s"\'<>]*\.pdf[^\s"\'<>]*', html, re.IGNORECASE)
        static_mentions = re.findall(r'https?://static[^\s"\'<>]*ara\.cat[^\s"\'<>]*', html, re.IGNORECASE)

        print(f"URLs de PDF directes: {pdf_mentions}")
        print(f"URLs de static.ara.cat: {static_mentions[:10]}")

        # Buscar enllaços candidats
        links = await page.query_selector_all("a")
        pdf_url = None
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()[:60]
            if any(x in href.lower() for x in ["pdf", "paper", "download"]):
                print(f"  [CANDIDAT href] [{text}] -> {href}")
                if not pdf_url:
                    pdf_url = href if href.startswith("http") else "https://www.ara.cat" + href

        # Si no trobem PDF als hrefs, intentar clicar la imatge de l'última edició
        if not pdf_url:
            print("No trobat per href, intentant descàrrega via clic a la imatge/botó...")
            try:
                async with page.expect_download(timeout=20000) as dl:
                    # Provar diversos selectors per la imatge/botó de descàrrega
                    for selector in [
                        ".hemeroteca a",
                        "a:has(img)",
                        ".edicio-paper a",
                        ".paper-edition a",
                        "a[href*='hemeroteca']",
                    ]:
                        try:
                            await page.click(selector, timeout=5000)
                            print(f"Clicat: {selector}")
                            break
                        except:
                            pass
                download = await dl.value
                fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
                await download.save_as(fitxer_pdf)
                await browser.close()
                print(f"PDF desat a: {fitxer_pdf}")
                return fitxer_pdf
            except Exception as e:
                print(f"Error descàrrega via clic: {e}")
                # Mostrar tots els enllaços per diagnòstic
                for link in links:
                    href = await link.get_attribute("href") or ""
                    text = (await link.inner_text()).strip()[:60]
                    if href and href != "#":
                        print(f"  [{text}] -> {href}")
                raise Exception("No s'ha pogut descarregar el PDF.")

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
