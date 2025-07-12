import os
import re
import time
import base64
import tempfile
import requests
import markdown
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from docx import Document

app = FastAPI()

# Тепер нам не потрібен ключ CloudConvert,
# але можна лишити для PDF-версії.
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

class PdfRequest(BaseModel):
    title: str
    instructions: str | None = None
    content: str

def slugify(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_') or 'document'

@app.post("/generate-docx")
def generate_docx(data: PdfRequest):
    """
    Генерує .docx з вашими заголовком, інструкціями та Markdown-контентом,
    завантажує на transfer.sh і повертає URL.
    """
    # 1) Створюємо новий Word-документ
    doc = Document()
    doc.add_heading(data.title, level=1)

    if data.instructions:
        doc.add_heading("Інструкції", level=2)
        for line in data.instructions.splitlines():
            doc.add_paragraph(line)

    # Markdown → plain paragraphs, простий парсер
    html = markdown.markdown(data.content, extensions=["extra", "sane_lists"])
    # Видаляємо теги HTML, залишаємо текст і списки
    # (для спрощення розіб’ємо по рядках)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for elem in soup.find_all(["h1","h2","h3","p","li","pre","code"]):
        text = elem.get_text()
        if elem.name.startswith("h"):
            level = int(elem.name[1])
            doc.add_heading(text, level=min(level,3))
        else:
            doc.add_paragraph(text)

    # 2) Зберігаємо тимчасово на диск
    slug = slugify(data.title)
    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_path = tmp.name
    tmp.close()
    doc.save(tmp_path)

    # 3) Завантажуємо на transfer.sh
    with open(tmp_path, "rb") as f:
        r = requests.put(f"https://transfer.sh/{slug}.docx", data=f)
    if r.status_code not in (200,201):
        raise HTTPException(500, detail=f"Upload failed: {r.text}")
    url = r.text.strip()

    # 4) Повертаємо посилання
    return {"url": url}
