"""PDF text extraction with optional OCR for scanned pages."""
import os
from .base import AnnotationProvider, Proposal
class DocumentProvider(AnnotationProvider):
    name="document-pipeline-v2"; supported_modalities=("document",)
    def annotate(self,sample,file_path):
        try:
            import fitz
            doc=fitz.open(file_path); pages=[]; full=[]
            for i,page in enumerate(doc):
                text=page.get_text("text") or ""; method="pdf_text_layer"
                if len(text.strip())<20 and os.getenv("THEO_ENABLE_OCR","false").lower()=="true":
                    try:
                        import pytesseract
                        from PIL import Image
                        pix=page.get_pixmap(matrix=fitz.Matrix(2,2)); img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
                        text=pytesseract.image_to_string(img); method="tesseract_ocr"
                    except Exception: method="ocr_unavailable"
                extracted_tables=[]
                try:
                    found=page.find_tables()
                    extracted_tables=[table.extract() for table in found.tables]
                except Exception:
                    pass
                pages.append({"page":i+1,"characters":len(text),"text":text[:10000],"extraction_method":method,"tables":extracted_tables}); full.append(text)
            metadata={"page_count":len(doc),"metadata":doc.metadata or {}}; doc.close()
            text="\n".join(full)
            return Proposal({"task":"document_extraction","metadata":metadata,"pages":pages,"characters_extracted":len(text)},None,{"method":"PyMuPDF with optional Tesseract OCR","ocr_enabled":os.getenv("THEO_ENABLE_OCR","false").lower()=="true","warning":"OCR text requires review; extracted table grids are heuristic and complex layout semantics are not guaranteed."},provider=self.name)
        except Exception as exc:
            return Proposal({"task":"document_extraction","valid":False,"error":str(exc)[:300]},None,{"method":"PyMuPDF"},provider=self.name)
