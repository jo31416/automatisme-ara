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

        # Interceptar totes les peticions de xarxa per trobar el PDF
        pdf_urls_xarxa = []
        api_urls = []

        def on_request(request):
            url = request.url
            if ".pdf" in url.lower():
                print(f"  [REQUEST PDF] {url}")
                pdf_urls_xarxa.append(url)
            if "hemeroteca" in url.lower() and ("api" in url.lower() or "json" in url.lower()):
                print(f"  [REQUEST API] {url}")
                api_urls.append(url)

        def on_response(response):
            url = response.url
            if ".pdf" in url.lower():
                print(f"  [RESPONSE PDF] {url}")

        page.on("request", on_request)
        page.on("response", on_response)

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

        # Esperar contingut dinàmic i interceptar peticions
        print("Esperant contingut dinàmic (15s)...")
        await asyncio.sleep(15)

        print(f"\nPDFs capturats per xarxa: {pdf_urls_xarxa}")
        print(f"APIs capturades: {api_urls}")

        # 3. BUSCAR EL PDF
        pdf_url = None

        # Primer: PDFs interceptats per xarxa
        if pdf_urls_xarxa:
            pdf_url = pdf_urls_xarxa[0]

        # Segon: buscar a les APIs capturades
        if not pdf_url and api_urls:
            import urllib.request
            for api_url in api_urls:
                try:
                    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req) as resp:
                        data = resp.read().decode("utf-8")
                        pdf_match = re.search(r'https?://[^\s"\'<>]*\.pdf[^\s"\'<>]*', data)
                        if pdf_match:
                            pdf_url = pdf_match.group(0)
                            print(f"PDF trobat a API: {pdf_url}")
                            break
                except:
                    pass

        # Tercer: buscar al HTML final
        if not pdf_url:
            html = await page.content()
            pdf_match = re.search(r'https?://[^\s"\'<>]*\.pdf[^\s"\'<>]*', html, re.IGNORECASE)
            if pdf_match:
                pdf_url = pdf_match.group(0)

        if not pdf_url:
            # Intentar clicar la imatge de portada i capturar la descàrrega
            print("Intentant clicar la portada de l'última edició...")
            try:
                async with page.expect_download(timeout=15000) as dl:
                    await page.click(".hemeroteca-paper a, .paper a, .edicio a, a:has(img[src*='clip'])", timeout=10000)
                download = await dl.value
                fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
                await download.save_as(fitxer_pdf)
                await browser.close()
                return fitxer_pdf
            except Exception as e:
                print(f"Error clic portada: {e}")
                raise Exception("No s'ha trobut el PDF per cap mètode.")

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
