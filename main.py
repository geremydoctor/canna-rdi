from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import os

app = FastAPI()

CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

class PdfRequest(BaseModel):
    title: str
    content: str

@app.post("/generate")
def generate_pdf(data: PdfRequest):
    payload = {
        "tasks": {
            "html": {
                "operation": "import/html",
                "html": f"<h1>{data.title}</h1><div>{data.content.replace('\n','<br>')}</div>"
            },
            "pdf": {
                "operation": "convert",
                "input": "html",
                "input_format": "html",
                "output_format": "pdf"
            },
            "export": {
                "operation": "export/url",
                "input": "pdf"
            }
        }
    }

    headers = {"Authorization": f"Bearer {CLOUDCONVERT_API_KEY}"}
    res = requests.post("https://api.cloudconvert.com/v2/jobs", json=payload, headers=headers)
    export_url = res.json()["data"]["tasks"][-1]["result"]["files"][0]["url"]
    return {"url": export_url}
