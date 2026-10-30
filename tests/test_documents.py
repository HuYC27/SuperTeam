import tempfile
import unittest
import zipfile
from pathlib import Path
from uploads import extract_text

class DocumentTests(unittest.TestCase):
    def test_docx_body_is_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.docx'
            with zipfile.ZipFile(path,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX-712</w:t></w:r></w:p></w:body></w:document>')
            self.assertIn('DOCX-712',extract_text(path)[0])
    def test_xlsx_values_are_extracted(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.xlsx';book=Workbook();book.active['A1']='DATA-314';book.active['B1']=42;book.save(path);book.close()
            text,_=extract_text(path);self.assertIn('DATA-314',text);self.assertIn('42',text)
    def test_pdf_body_is_extracted(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.pdf';writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 14 Tf 20 100 Td (PDF-FIXTURE-381) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream);writer.write(path);writer.close()
            self.assertIn('PDF-FIXTURE-381',extract_text(path)[0])

if __name__=='__main__':unittest.main()
