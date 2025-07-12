import os
import re
import tempfile
import traceback
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import markdown
from docx import Document
from bs4 import BeautifulSoup

app = FastAPI()

def slugify(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_') or 'document'

class PdfRequest(BaseModel):
    title: str
    instructions: str | None = None
    content: str

@app.post("/generate-docx")
def generate_docx(data: PdfRequest):
    try:
        # 1) Створюємо Word-документ
        doc = Document()
        doc.add_heading(data.title, level=1)

        if data.instructions:
            doc.add_heading("Інструкції", level=2)
            for line in data.instructions.splitlines():
                doc.add_paragraph(line)

        # 2) Markdown → HTML → текстові блоки
        html = markdown.markdown(data.content, extensions=["extra", "sane_lists", "fenced_code"])
        soup = BeautifulSoup(html, "html.parser")

        for elem in soup.find_all(["h1","h2","h3","p","li","pre","code"]):
            text = elem.get_text()
            if elem.name.startswith("h"):
                level = min(int(elem.name[1]), 3)
                doc.add_heading(text, level=level)
            else:
                doc.add_paragraph(text)

        # 3) Зберігаємо файл тимчасово
        slug = slugify(data.title)
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp_path = tmp.name
        tmp.close()
        doc.save(tmp_path)

        # 4) Завантажуємо на transfer.sh
        with open(tmp_path, "rb") as f:
            resp = requests.put(f"https://transfer.sh/{slug}.docx", data=f)
        if resp.status_code not in (200, 201):
            raise HTTPException(500, detail=f"Upload failed: {resp.status_code} {resp.text}")

        url = resp.text.strip()
        return {"url": url}

    except Exception as e:
        # Друк повного трабеку в логах Render
        print("=== Exception in /generate-docx ===")
        traceback.print_exc()
        # Повертаємо клієнту помилку з текстом
        raise HTTPException(500, detail=str(e))
