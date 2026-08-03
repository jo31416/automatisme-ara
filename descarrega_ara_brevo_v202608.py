import os
import asyncio
import re
import json
import base64
import smtplib
import urllib.request
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from playwright.async_api import async_playwright

BREVO_SMTP_LOGIN = os.environ["BREVO_SMTP_LOGIN"]
BREVO_FROM = os.environ["BREVO_FROM"]
BREVO_SMTP_KEY = os.environ["BREVO_SMTP_KEY"]
DESTINATARIS = os.environ["DESTINATARIS"].split(",")

ARA_USUARI = os.environ["ARA_USUARI"]
ARA_PASSWORD = os.environ["ARA_PASSWORD"]

CARPETA_DESAR = "/tmp"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def esta_loguejat(page):
    html = await page.content()
    if "inicia-sessio" in html.lower() or "inicia sessió" in html.lower() or "Necessites ajuda per iniciar sessió" in html:
        return False
    return True


async def api_get_text(page, url):
    """Fa la crida GET des de dins del navegador (mateix fingerprint/cookies que la navegació)."""
    return await page.evaluate(
        """async (url) => {
            const resp = await fetch(url, { headers: { "Accept": "application/json" } });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            return await resp.text();
        }""",
        url,
    )


async def api_get_binary(page, url):
    """Fa la crida GET binaria (PDF) des de dins del navegador i la retorna com a bytes."""
    b64 = await page.evaluate(
        """async (url) => {
            const resp = await fetch(url, { headers: { "Accept": "application/pdf,*/*" } });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const buf = await resp.arrayBuffer();
            let binary = "";
            const bytes = new Uint8Array(buf);
            for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
            return btoa(binary);
        }""",
        url,
    )
    return base64.b64decode(b64)


async def descarrega_pdf():
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
        except Exception:
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
            except Exception:
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
        print(f"Cookies: {len([c for c in cookies if 'ara.cat' in c.get('domain', '')])} cookies d'ara.cat")

        # 4. OBTENIR ID DE PUBLICACIÓ (crida feta des del navegador per evitar el 403)
        print("Obtenint ID de la publicació...")
        body = await api_get_text(page, "https://www.ara.cat/api/front/archive/publications?limit=5")
        data_json = json.loads(body)
        items = data_json["response"]["items"]

        pub_id = None
        for item in items:
            if item.get("type", {}).get("value") == "ara":
                pub_id = item["id"]
                print(f"Publicació principal trobada: {item['pdf']['filename']} (id={pub_id})")
                break

        if pub_id is None:
            raise Exception("No s'ha trobat cap publicació de tipus 'ara'.")

        # 5. DESCARREGAR EL PDF (també des del navegador)
        print("Descarregant PDF...")
        pdf_data = await api_get_binary(page, f"https://www.ara.cat/api/front/archive/publication/{pub_id}")
        print(f"Bytes rebuts: {len(pdf_data)} — Inici: {pdf_data[:10]}")

        if not pdf_data.startswith(b'%PDF'):
            raise Exception(f"La resposta no és un PDF: {pdf_data[:100]}")

        avui = date.today()
        fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{avui}.pdf")
        with open(fitxer_pdf, "wb") as f:
            f.write(pdf_data)

        await browser.close()

        mida = os.path.getsize(fitxer_pdf)
        print(f"PDF desat: {fitxer_pdf} ({mida:,} bytes)")
        return fitxer_pdf


def envia_email(fitxer_pdf):
    avui = date.today().strftime("%d/%m/%Y")
    assumpte = f"Diari Ara — {avui}"
    cos = f"Bon dia,\n\nAdjunt trobaràs l'edició del diari Ara del {avui}.\n\nBona lectura!"

    msg = MIMEMultipart()
    msg["From"] = BREVO_FROM
    msg["To"] = ", ".join(DESTINATARIS)
    msg["Subject"] = assumpte
    msg.attach(MIMEText(cos, "plain", "utf-8"))

    with open(fitxer_pdf, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    nom_fitxer = os.path.basename(fitxer_pdf)
    part.add_header("Content-Disposition", f'attachment; filename="{nom_fitxer}"')
    msg.attach(part)

    print("Enviant email via Brevo SMTP...")
    with smtplib.SMTP("smtp-relay.brevo.com", 587) as servidor:
        servidor.starttls()
        servidor.login(BREVO_SMTP_LOGIN, BREVO_SMTP_KEY)
        servidor.sendmail(BREVO_FROM, DESTINATARIS, msg.as_string())
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
