import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

# Завантажуємо .env при локальному тестуванні (на Render ця змінна середовища читається автоматично)
load_dotenv()

app = FastAPI()
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

@app.get("/health")
def health_check():
    """
    Перевірка стану сервісу й коректності ключа.
    """
    return {
        "status": "ok",
        "has_key": bool(CLOUDCONVERT_API_KEY),
        "key_preview": CLOUDCONVERT_API_KEY[:5] if CLOUDCONVERT_API_KEY else ""
    }

class PdfRequest(BaseModel):
    title: str
    content: str

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    """
    Приймає JSON { title, content }, відправляє job у CloudConvert,
    чекає на завершення і повертає пряме посилання на PDF.
    """
    if not CLOUDCONVERT_API_KEY:
        raise HTTPException(500, detail="CloudConvert API key not configured")

    # Формуємо HTML
    html = f"<h1>{data.title}</h1><div>{data.content.replace(chr(10), '<br>')}</div>"

    # Створюємо Job
    payload = {
        "tasks": {
            "html": {
                "operation": "import/html",
                "html": html
            },
            "pdf": {
                "operation": "convert",
                "input": "html",
                "input_format": "html",
                "output_format": "pdf"
            },
            "export": {
                "operation": "export/url",
                "input": "pdf",
                "inline": True   # повернути пряме посилання
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

    job = resp.json()["data"]
    job_id = job["id"]

    # Чекаємо завершення завдання (до 30 секунд)
    for _ in range(30):
        time.sleep(1)
        status_resp = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers)
        if status_resp.status_code != 200:
            continue
        status = status_resp.json()["data"]
        if status["status"] == "finished":
            break
        if status["status"] == "error":
            raise HTTPException(500, detail="CloudConvert job failed")
    else:
        raise HTTPException(500, detail="CloudConvert job did not finish in time")

    # Знаходимо export-задачу та дістаємо URL
    export_task = next(
        (t for t in status["tasks"] if t["operation"] == "export/url"),
        None
    )
    if not export_task or "result" not in export_task:
        raise HTTPException(500, detail="Export task missing in job response")

    file_url = export_task["result"]["files"][0]["url"]
    return {"url": file_url}
