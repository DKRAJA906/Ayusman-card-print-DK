
import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

app = FastAPI(
    title="DK JAN SUVIDHA KENDRA",
    description="Ayushman Card Print Tool"
)

# Project directory
BASE_DIR = Path(__file__).resolve().parent

# A4 Page Size (Points)
A4_WIDTH = 595.28
A4_HEIGHT = 841.89

# Sample Ayushman PDF Crop Positions
# These positions match the PDF you provided.
FRONT_BOX = (105, 95, 411, 249)
BACK_BOX = (445, 95, 752, 249)


# Rounded Corner Function
def rounded_card(img, radius=24):

    img = img.convert("RGBA")

    mask = Image.new("L", img.size, 0)

    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        (0, 0, img.width - 1, img.height - 1),
        radius=radius,
        fill=255
    )

    img.putalpha(mask)

    return img


# Crop Card Function
def crop_card(image, box):

    return image.crop(box)


# Home Page Route
@app.get("/", include_in_schema=False)
async def home():

    html_file = BASE_DIR /"static"/ "index.html"

    if not html_file.exists():
        raise HTTPException(
            status_code=500,
            detail="index.html file not found"
        )

    return FileResponse(
        str(html_file),
        media_type="text/html"
    )


# Health Check
@app.get("/health")
async def health():

    return {
        "status": "online",
        "service": "DK Ayushman Card Print"
    }


# Ayushman PDF Print API
@app.post("/api/ayushman-a4")
async def ayushman_print(
    file: UploadFile = File(...)
):

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    data = await file.read()

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Empty PDF file"
        )

    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file"
        )

    doc = None
    output = None

    try:

        # Open Uploaded PDF
        doc = fitz.open(
            stream=data,
            filetype="pdf"
        )

        if len(doc) < 1:
            raise ValueError("PDF has no pages")

        page = doc[0]

        # High Quality Rendering
        pix = page.get_pixmap(
            matrix=fitz.Matrix(3, 3),
            alpha=False
        )

        image = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        # Crop positions are based on
        # the supplied sample PDF (850 x 300 points).
        scale_x = image.width / page.rect.width
        scale_y = image.height / page.rect.height

        front_box = tuple(
            round(v * (scale_x if i % 2 == 0 else scale_y))
            for i, v in enumerate(FRONT_BOX)
        )

        back_box = tuple(
            round(v * (scale_x if i % 2 == 0 else scale_y))
            for i, v in enumerate(BACK_BOX)
        )

        # Extract Front and Back
        front = crop_card(image, front_box)
        back = crop_card(image, back_box)

        # Rounded Corners
        front = rounded_card(front)
        back = rounded_card(back)

        # Create A4 PDF
        output = fitz.open()

        pdf_page = output.new_page(
            width=A4_WIDTH,
            height=A4_HEIGHT
        )

        # Card Size
        card_width = 250

        card_height = card_width * (
            front.height / front.width
        )

        gap = 14

        total_width = (
            card_width * 2 + gap
        )

        # Center Alignment
        start_x = (
            A4_WIDTH - total_width
        ) / 2

        start_y = 25

        cards = [front, back]

        # Insert Both Cards
        for i, card in enumerate(cards):

            buffer = io.BytesIO()

            card.save(
                buffer,
                format="PNG"
            )

            buffer.seek(0)

            x = start_x + i * (
                card_width + gap
            )

            rect = fitz.Rect(
                x,
                start_y,
                x + card_width,
                start_y + card_height
            )

            pdf_page.insert_image(
                rect,
                stream=buffer.getvalue(),
                keep_proportion=True
            )

        # Generate Final PDF
        result = output.tobytes(
            garbage=4,
            deflate=True
        )

        return StreamingResponse(
            io.BytesIO(result),
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                'attachment; filename="DK_Ayushman_Card.pdf"'
            }
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=f"PDF Processing Error: {str(e)}"
        )

    finally:

        if doc is not None:
            doc.close()

        if output is not None:
            output.close()
