name: Diagnostic Publications API

on:
  workflow_dispatch:

jobs:
  diagnostic:
    runs-on: ubuntu-latest

    steps:
      - name: Descarrega el codi
        uses: actions/checkout@v4

      - name: Configura Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Instal·la dependències
        run: |
          pip install playwright
          python -m playwright install chromium
          python -m playwright install-deps chromium

      - name: Executa diagnòstic
        env:
          ARA_USUARI: ${{ secrets.ARA_USUARI }}
          ARA_PASSWORD: ${{ secrets.ARA_PASSWORD }}
        run: python diagnostic.py
