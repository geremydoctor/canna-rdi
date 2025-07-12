import os
import time
import base64
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

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
    content: str

def slugify(text: str) -> str:
    """
    Перетворює будь-який рядок у "slug" з ASCII:
    залишає тільки латиницю, цифри та підкреслення.
    """
    slug = re.sub(r'[^A-Za-z0-9]+', '_', text)
    return slug.strip('_') or 'document'

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    if not CLOUDCONVERT_API_KEY:
        raise HTTPException(500, detail="CloudConvert API key not configured")

    # 1) Формуємо HTML і конвертуємо в base64
    html = f"<h1>{data.title}</h1><div>{data.content.replace(chr(10), '<br>')}</div>"
    encoded_html = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    # 2) Генеруємо "slug" з заголовку для імені файлів
    slug = slugify(data.title)
    html_filename = f"{slug}.html"
    # CloudConvert автоматично замінить розширення на .pdf при конвертації

    # 3) Створюємо Job у CloudConvert
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

    # 4) Чекаємо завершення job (до ~30 сек)
    for _ in range(30):
        time.sleep(1)
        status = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers).json()["data"]
        if status["status"] == "finished":
            break
        if status["status"] == "error":
            raise HTTPException(500, detail="CloudConvert job failed")
    else:
        raise HTTPException(500, detail="CloudConvert job did not finish in time")

    # 5) Забираємо URL із задачі export/url
    export_task = next((t for t in status["tasks"] if t["operation"] == "export/url"), None)
    if not export_task or "result" not in export_task:
        raise HTTPException(500, detail="Export task missing")

    file_url = export_task["result"]["files"][0]["url"]
    return {"url": file_url}
