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

            print("Anant a l'hemeroteca...")
            await page.goto("https://www.ara.cat/hemeroteca/", wait_until="domcontentloaded", timeout=60000)

        await asyncio.sleep(10)

        # 3. INTERCEPTAR LA CRIDA A L'API DE PUBLICACIÓ
        print("Buscant l'ID de la publicació al HTML...")
        html = await page.content()

        # Buscar IDs de publicació al HTML
        pub_ids = re.findall(r'/api/front/archive/publication/(\d+)', html)
        print(f"IDs de publicació trobats al HTML: {pub_ids}")

        if not pub_ids:
            # Interceptar la crida mentre es fa clic a la portada
            print("No trobat al HTML, interceptant via clic...")
            pub_ids_xarxa = []

            async def on_request(request):
                url = request.url
                m = re.search(r'/api/front/archive/publication/(\d+)', url)
                if m:
                    print(f"  [API] {url}")
                    pub_ids_xarxa.append(m.group(1))

            page.on("request", on_request)

            try:
                await page.click("a:has(img[src*='clip'])", timeout=15000)
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error clic: {e}")

            pub_ids = pub_ids_xarxa

        if not pub_ids:
            raise Exception("No s'ha trobat l'ID de publicació.")

        pub_id = pub_ids[0]
        print(f"ID de publicació: {pub_id}")

        # 4. CRIDAR L'API PER OBTENIR L'URL SIGNADA DEL PDF
        api_url = f"https://www.ara.cat/api/front/archive/publication/{pub_id}"
        print(f"Cridant API: {api_url}")

        api_response = await page.evaluate(f"""
            async () => {{
                const resp = await fetch('{api_url}', {{
                    credentials: 'include',
                    headers: {{ 'Accept': 'application/json' }}
                }});
                return await resp.text();
            }}
        """)
        print(f"Resposta API (primers 500 chars): {api_response[:500]}")

        # Parsejar la resposta
        try:
            data = json.loads(api_response)
        except:
            # Buscar URL directament al text
            match = re.search(r'https://aranx-data[^\s"\'<>]+\.pdf[^\s"\'<>]*', api_response)
            if match:
                pdf_url = match.group(0)
            else:
                raise Exception(f"No s'ha pogut parsejar la resposta: {api_response[:300]}")
        else:
            # Buscar l'URL del PDF a la resposta JSON
            api_str = json.dumps(data)
            match = re.search(r'https://aranx-data[^"\'<>\s]+\.pdf[^"\'<>\s]*', api_str)
            if match:
                pdf_url = match.group(0)
            else:
                print(f"Resposta completa: {api_str[:1000]}")
                raise Exception("No s'ha trobat l'URL del PDF a la resposta de l'API.")

        print(f"URL del PDF: {pdf_url[:80]}...")

        # 5. DESCARREGAR EL PDF
        import urllib.request
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req) as response:
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
