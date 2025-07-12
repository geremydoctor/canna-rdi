import re
import io
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import markdown
from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.shared import Pt

app = FastAPI()

class Message(BaseModel):
    speaker: str
    text: str
    timestamp: str | None = None

class CompileRequest(BaseModel):
    title: str
    messages: list[Message]

def slugify(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_') or 'document'

def add_html_to_doc(doc: Document, html: str):
    soup = BeautifulSoup(html, "html.parser")
    for elem in soup.children:
        if isinstance(elem, NavigableString):
            doc.add_paragraph(str(elem))
            continue
        if not isinstance(elem, Tag):
            continue

        if elem.name == "h1":
            doc.add_heading(elem.get_text(), level=2)
        elif elem.name in ("h2", "h3"):
            doc.add_heading(elem.get_text(), level=3)
        elif elem.name == "ul":
            for li in elem.find_all("li", recursive=False):
                doc.add_paragraph(li.get_text(), style="List Bullet")
        elif elem.name == "ol":
            for li in elem.find_all("li", recursive=False):
                doc.add_paragraph(li.get_text(), style="List Number")
        elif elem.name == "pre":
            code = elem.get_text()
            p = doc.add_paragraph()
            run = p.add_run(code)
            run.font.name = "Courier New"
            run.font.size = Pt(10)
        else:
            p = doc.add_paragraph()
            def recurse(node):
                if isinstance(node, NavigableString):
                    p.add_run(str(node))
                elif isinstance(node, Tag):
                    run = p.add_run(node.get_text())
                    if node.name in ("strong", "b"):
                        run.bold = True
                    if node.name in ("em", "i"):
                        run.italic = True
                    if node.name == "code":
                        run.font.name = "Courier New"
                        run.font.size = Pt(10)
                    for child in node.contents:
                        recurse(child)
            for child in elem.contents:
                recurse(child)

@app.post("/compileChatToDocx")
def compile_chat(req: CompileRequest):
    """
    Приймає title та масив повідомлень, збирає DOCX в пам’яті та повертає його як attachment.
    """
    try:
        doc = Document()
        doc.add_heading(req.title, level=1)

        for msg in req.messages:
            header = msg.speaker + (f" [{msg.timestamp}]" if msg.timestamp else "")
            p = doc.add_paragraph()
            run = p.add_run(header + ": ")
            run.bold = True

            html = markdown.markdown(
                msg.text,
                extensions=["extra", "sane_lists", "fenced_code"]
            )
            add_html_to_doc(doc, html)

        # Збережемо у BytesIO
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)

        filename = f"{slugify(req.title)}.docx"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
        return StreamingResponse(
            bio,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )

    except Exception as e:
        raise HTTPException(500, detail=str(e))
