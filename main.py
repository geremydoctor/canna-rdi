import os
import time
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

    html = f"<h1>{data.title}</h1><div>{data.content.replace(chr(10), '<br>')}</div>"

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

    job = resp.json()["data"]
    job_id = job["id"]

    for _ in range(30):
        time.sleep(1)
        status = requests.get(f"https://api.cloudconvert.com/v2/jobs/{job_id}", headers=headers).json()["data"]
        if status["status"] == "finished":
            break
        if status["status"] == "error":
            raise HTTPException(500, detail="CloudConvert job failed")
    else:
        raise HTTPException(500, detail="CloudConvert job did not finish in time")

    export_task = next((t for t in status["tasks"] if t["operation"] == "export/url"), None)
    if not export_task or "result" not in export_task:
        raise HTTPException(500, detail="Export task missing")

    return {"url": export_task["result"]["files"][0]["url"]}
