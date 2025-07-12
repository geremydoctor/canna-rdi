import os
import time
import base64
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

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    if not CLOUDCONVERT_API_KEY:
        raise HTTPException(500, detail="CloudConvert API key not configured")

    # Формуємо HTML і кодуємо його в base64
    html = f"<h1>{data.title}</h1><div>{data.content.replace(chr(10), '<br>')}</div>"
    encoded_html = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    # Відправляємо job із трьома завданнями: імпорт, конвертація, експорт
    payload = {
        "tasks": {
            "import-html": {
                "operation": "import/base64",
                "file": encoded_html,
                "filename": f"{data.title}.html"
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

    # Створюємо job
    resp = requests.post("https://api.cloudconvert.com/v2/jobs", json=payload, headers=headers)
    if resp.status_code != 201:
        raise HTTPException(resp.status_code, detail=f"Job creation failed: {resp.text}")

    job_id = resp.json()["data"]["id"]

    # Чекаємо завершення job (до ~30 сек)
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

    # Будь-який таск з operation == export/url має наше посилання
    export_task = next(t for t in job_data["tasks"] if t["operation"] == "export/url")
    file_url = export_task["result"]["files"][0]["url"]

    return {"url": file_url}
