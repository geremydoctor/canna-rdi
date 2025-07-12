import os
import re
import tempfile
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
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
    """
    Створюємо .docx і повертаємо як файл.
    """
    try:
        # 1) Створюємо Word-документ
        doc = Document()
        doc.add_heading(data.title, level=1)

        if data.instructions:
            doc.add_heading("Інструкції", level=2)
            for line in data.instructions.splitlines():
                doc.add_paragraph(line)

        # 2) Markdown → HTML → текстові блоки
        html = markdown.markdown(
            data.content,
            extensions=["extra", "sane_lists", "fenced_code"]
        )
        soup = BeautifulSoup(html, "html.parser")
        for elem in soup.find_all(["h1","h2","h3","p","li","pre","code"]):
            text = elem.get_text()
            if elem.name.startswith("h"):
                level = min(int(elem.name[1]), 3)
                doc.add_heading(text, level=level)
            else:
                doc.add_paragraph(text)

        # 3) Зберігаємо локально у тимчасовий файл
        slug = slugify(data.title)
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp_path = tmp.name
        tmp.close()
        doc.save(tmp_path)

        # 4) Повертаємо файл напряму через FileResponse
        return FileResponse(
            tmp_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{slug}.docx"
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=str(e))
