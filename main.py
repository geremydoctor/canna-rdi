import os
import time
import base64
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import markdown

app = FastAPI()
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

@app.get("/health")
def health_check():
    """
    Перевіряє, чи підхоплено API-ключ.
    """
    return {
        "status": "ok",
        "has_key": bool(CLOUDCONVERT_API_KEY),
        "key_preview": CLOUDCONVERT_API_KEY[:5] if CLOUDCONVERT_API_KEY else ""
    }

class PdfRequest(BaseModel):
    title: str
    instructions: str | None = None
    content: str

def slugify(text: str) -> str:
    """
    Перетворює рядок у короткий ASCII-slug для імені файлу.
    """
    slug = re.sub(r'[^A-Za-z0-9]+', '_', text)
    return slug.strip('_') or 'document'

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    """
    Приймає title, опціональні instructions і content (Markdown),
    конвертує в HTML із CSS-стилями, потім у PDF через CloudConvert,
    і повертає пряме посилання.
    """
    if not CLOUDCONVERT_API_KEY:
        raise HTTPException(500, detail="CloudConvert API key not configured")

    # 1) Markdown → HTML для основного контенту
    html_content = markdown.markdown(
        data.content,
        extensions=["extra", "sane_lists", "fenced_code"]
    )

    # 2) Markdown → HTML для інструкцій (якщо є)
    html_instructions = ""
    if data.instructions:
        instr_html = markdown.markdown(
            data.instructions,
            extensions=["extra", "sane_lists"]
        )
        html_instructions = f"<h2>Інструкції</h2>{instr_html}"

    # 3) Додаємо CSS-стилі і збираємо повний HTML-документ
    css = """
    <style>
      body { font-family: 'Georgia', serif; margin: 40px; }
      h1 { color: #34495e; text-align: center; }
      h2 { color: #2c3e50; margin-top: 30px; }
      ul, ol { margin-left: 20px; }
      pre, code { font-family: 'Courier New', monospace; background: #f4f4f4; padding: 6px; }
      header { text-align: center; margin-bottom: 30px; }
      footer { text-align: center; font-size: 0.8em; margin-top: 30px; color: #777; }
    </style>
    """
    html = (
        "<html><head>" + css + "</head><body>"
        "<header><h1>" + data.title + "</h1></header>"
        + html_instructions +
        html_content +
        "<footer>Згенеровано за допомогою GPT-PDF-Generator</footer>"
        + "</body></html>"
    )

    # 4) Кодуємо HTML у Base64 для імпорту
    encoded_html = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    # 5) Формуємо ім'я файлу на основі заголовка
    slug = slugify(data.title)
    html_filename = f"{slug}.html"

    # 6) Створюємо Job у CloudConvert
    payload = {
        "tasks": {
            "import-html": {
                "operation": "import/base64",
                "file": encoded_html,
                "filename": html_filename
            },
            "convert-pdf": {
                "operation": "convert",
                "input": "import-html",
                "input_format": "html",
                "output_format": "pdf"
            },
            "export-pdf": {
                "operation": "export/url",
                "input": "convert-pdf",
                "inline": True
            }
        }
    }
    headers = {
        "Authorization": f"Bearer {CLOUDCONVERT_API_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post("https://api.cloudconvert.com/v2/jobs", json=payload, headers=headers)
    if resp.status_code != 201:
        raise HTTPException(resp.status_code, detail=f"Job creation failed: {resp.text}")

    job_id = resp.json()["data"]["id"]

    # 7) Чекаємо завершення job (до 30 секунд)
    for _ in range(30):
        time.sleep(1)
        status_resp = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers)
        if status_resp.status_code != 200:
            continue
        job_data = status_resp.json()["data"]
        if job_data["status"] == "finished":
            break
        if job_data["status"] == "error":
            raise HTTPException(500, detail="CloudConvert job failed")
    else:
        raise HTTPException(500, detail="CloudConvert job did not finish in time")

    # 8) Отримуємо URL експорту PDF
    export_task = next((t for t in job_data["tasks"] if t["operation"] == "export/url"), None)
    if not export_task or "result" not in export_task:
        raise HTTPException(500, detail="Export task missing in job response")

    file_url = export_task["result"]["files"][0]["url"]
    return {"url": file_url}
