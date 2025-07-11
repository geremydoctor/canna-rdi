from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
import time

app = FastAPI()
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

class PdfRequest(BaseModel):
    title: str
    content: str

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    # 1. Формуємо HTML з заголовком і контентом
    html = f"<h1>{data.title}</h1><div>{data.content.replace(chr(10), '<br>')}</div>"

    # 2. Створюємо Job у CloudConvert
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
                "inline": True           # ← додаємо inline
            }
        }
    }
    headers = {
        "Authorization": f"Bearer {CLOUDCONVERT_API_KEY}",
        "Content-Type": "application/json"
    }
    resp = requests.post("https://api.cloudconvert.com/v2/jobs", json=payload, headers=headers)
    if resp.status_code != 201:
        raise HTTPException(500, f"Job creation failed: {resp.text}")
    job = resp.json()["data"]

    # 3. Чекаємо, поки завдання завершиться
    job_id = job["id"]
    for _ in range(30):
        time.sleep(1)
        status = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers).json()["data"]
        if status["status"] == "finished":
            break
        if status["status"] == "error":
            raise HTTPException(500, "CloudConvert job error")

    # 4. Дістаємо посилання з export-завдання
    export_task = next(t for t in status["tasks"] if t["operation"] == "export/url")
    file_url = export_task["result"]["files"][0]["url"]

    return {"url": file_url}
