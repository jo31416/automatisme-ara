import os
import smtplib
import time
import urllib.request
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

import nest_asyncio
nest_asyncio.apply()

from playwright.sync_api import sync_playwright

# Les credencials vénen de les variables d'entorn (GitHub Secrets)
GMAIL_USUARI   = os.environ["GMAIL_USUARI"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
DESTINATARIS   = os.environ["DESTINATARIS"].split(",")
CARPETA_DESAR  = "/tmp"


def descarrega_pdf():
    """Obre la pàgina de l'hemeroteca i descarrega el PDF de l'última edició."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print("Obrint la pàgina de l'hemeroteca...")
        page.goto("https://www.ara.cat/hemeroteca/", wait_until="networkidle", timeout=60000)
        time.sleep(3)

        selectors = [
            "a[href*='.pdf']",
            "a[href*='pdf']",
            ".hemeroteca a",
            ".edicio a",
            "a.pdf",
            "a[download]",
        ]

        pdf_url = None
        for selector in selectors:
            links = page.query_selector_all(selector)
            for link in links:
                href = link.get_attribute("href") or ""
                if "pdf" in href.lower() or link.get_attribute("download"):
                    pdf_url = href if href.startswith("http") else "https://www.ara.cat" + href
                    break
            if pdf_url:
                break

        if not pdf_url:
            print("Intentant clicar botó de descàrrega...")
            with page.expect_download(timeout=60000) as download_info:
                page.click("a[href*='pdf'], .download-pdf, .btn-pdf", timeout=10000)
            download = download_info.value
            fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
            download.save_as(fitxer_pdf)
        else:
            print(f"URL del PDF trobat: {pdf_url}")
            fitxer_pdf = os.path.join(CARPETA_DESAR, f"ara_{date.today()}.pdf")
            urllib.request.urlretrieve(pdf_url, fitxer_pdf)

        browser.close()
        print(f"PDF desat a: {fitxer_pdf}")
        return fitxer_pdf


def envia_email(fitxer_pdf):
    """Envia el PDF per Gmail als destinataris configurats."""
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
    try:
        pdf = descarrega_pdf()
        envia_email(pdf)
        print("✓ Tot completat correctament.")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise

