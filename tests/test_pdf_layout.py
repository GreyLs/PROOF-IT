from io import BytesIO
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
from worker.pdf_layout import ordered_text


def test_two_columns_preserve_descenders_and_actual_spaces():
    font=Path(__file__).resolve().parents[1]/'deliverables/fonts/Montserrat-Regular.ttf'
    pdfmetrics.registerFont(TTFont('GeometryTest',str(font)))
    out=BytesIO();c=canvas.Canvas(out,pagesize=(595,842));c.setFont('GeometryTest',10)
    c.drawString(35,810,'Профиль профессионального опыта')
    left=[f'Опыт {i}: Python SQL проект 1' for i in range(1,10)]
    right=[f'Навыки {i}: Docker Git Linux 1' for i in range(1,10)]
    for i,(l,r) in enumerate(zip(left,right)):
        c.drawString(35,770-i*23,l);c.drawString(320,770-i*23,r)
    c.save()
    with pdfium.PdfDocument(out.getvalue()) as doc:
        page=doc[0];tp=page.get_textpage()
        try:text,method=ordered_text(tp)
        finally:tp.close();page.close()
    assert method=='pdf_geometry_two_column'
    positions=[text.index(line) for line in left+right]
    assert positions==sorted(positions)
    assert 'Профиль профессионального опыта' in text
