import os
import time
import base64
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import markdown  # імпорт для конвертації Markdown → HTML

app = FastAPI()
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "has_key": bool(CLOUDCONVERT_API_KEY),
        "key_preview": CLOUDCONVERT_API_KEY[:5] if CLOUDCONVERT_API_KEY else ""
    }

class PdfRequest(BaseModel):
    title: str
    instructions: str | None = None
    content: str  # тут ми приймаємо Markdown

def slugify(text: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '_', text)
    return slug.strip('_') or 'document'

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    if not CLOUDCONVERT_API_KEY:
        raise HTTPException(500, detail="CloudConvert API key not configured")

    # 1) Робимо Markdown → HTML
    # Конвертуємо основний контент
    html_content = markdown.markdown(data.content, extensions=["extra", "sane_lists"])
    # А також інструкції, якщо вони є
    html_instructions = ""
    if data.instructions:
        instr_html = markdown.markdown(data.instructions, extensions=["extra", "sane_lists"])
        html_instructions = f"<h2>Інструкції</h2>{instr_html}"

    # 2) Збираємо повне HTML-тіло
    html = f"<h1>{data.title}</h1>" + html_instructions + html_content

    # 3) Кодуємо HTML в Base64
    encoded = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    # 4) Генеруємо “slug” для імені файлу
    slug = slugify(data.title)
    filename = f"{slug}.html"

    # 5) Створюємо Job у CloudConvert
    payload = {
        "tasks": {
            "import-html": {
                "operation": "import/base64",
                "file": encoded,
                "filename": filename
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

    # 6) Чекаємо завершення job
    for _ in range(30):
        time.sleep(1)
        status = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers).json()["data"]
        if status["status"] == "finished":
            break
        if status["status"] == "error":
            raise HTTPException(500, detail="CloudConvert job failed")
    else:
        raise HTTPException(500, detail="Timeout waiting for CloudConvert job")

    # 7) Отримуємо URL
    export_task = next(t for t in status["tasks"] if t["operation"] == "export/url")
    file_url = export_task["result"]["files"][0]["url"]
    return {"url": file_url}
