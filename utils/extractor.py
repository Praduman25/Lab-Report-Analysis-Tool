import pdfplumber

#scanning pdf
def extract_text_from_pdf(file_path):
    text=""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text+=page.extract_text() or ""

    return text

#performing ocr
import pytesseract

from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_from_image(image_path):
    image=Image.open(image_path)
    text=pytesseract.image_to_string(image)
    return text

