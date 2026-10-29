import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

def iter_block_items(parent):
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)

doc = Document(sys.argv[1])
print("=== SECTIONS:", len(doc.sections))
for s in doc.sections:
    print("page", s.page_width, s.page_height, "margins", s.left_margin, s.right_margin, s.top_margin, s.bottom_margin)
print("=== HEADERS/FOOTERS")
for i, s in enumerate(doc.sections):
    for name in ('header', 'footer', 'first_page_header', 'first_page_footer'):
        part = getattr(s, name, None)
        if part is not None:
            txt = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            if txt.strip():
                print(f"[{i}.{name}] {txt!r}")
print("=== BODY")
n = 0
for block in iter_block_items(doc):
    if isinstance(block, Paragraph):
        n += 1
        style = block.style.name if block.style is not None else "?"
        text = block.text
        print(f"P{n:04d} [{style}] {text}")
    else:
        n += 1
        print(f"T{n:04d} === TABLE {len(block.rows)}x{len(block.columns)}")
        for r in block.rows:
            cells = []
            for c in r.cells:
                cells.append(c.text.replace("\n", " / "))
            print("   | " + " | ".join(cells))
