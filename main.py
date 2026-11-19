
import io
import fitz
from PIL import Image, ImageDraw

from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

app = FastAPI(
    title="DK JAN SUVIDHA KENDRA",
    description="Ayushman PVC Card Print"
)

BASE_DIR = Path(__file__).resolve().parent

# A4 Size in Points
A4_WIDTH = 595.28
A4_HEIGHT = 841.89

# Standard PVC Card Size
MM_TO_PT = 72 / 25.4

CARD_WIDTH = 85.60 * MM_TO_PT
CARD_HEIGHT = 53.98 * MM_TO_PT

# Card gap and top margin
GAP = 5 * MM_TO_PT
TOP_MARGIN = 10 * MM_TO_PT

# Original sample PDF dimensions: 850 x 300 points
# Front and Back crop positions
FRONT_BOX = (105, 95, 411, 249)
BACK_BOX = (445, 95, 752, 249)


# Rounded Corner Function


def rounded_card(img, radius=30):

    img = img.convert("RGBA")

    w, h = img.size

    # High quality anti-aliased mask
    scale = 4

    mask = Image.new(
        "L",
        (w * scale, h * scale),
        0
    )

    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        (0, 0, w * scale - 1, h * scale - 1),
        radius=radius * scale,
        fill=255
    )

    mask = mask.resize(
        (w, h),
        Image.Resampling.LANCZOS
    )

    img.putalpha(mask)

    # Thin border integrated inside card edge
    border = ImageDraw.Draw(img)

    border.rounded_rectangle(
        (2, 2, w - 3, h - 3),
        radius=radius,
        outline=(90, 90, 90, 255),
        width=2
    )

    return img




# Crop Function
def crop_card(image, box, scale_x, scale_y):

    x1, y1, x2, y2 = box

    coords = (
        round(x1 * scale_x),
        round(y1 * scale_y),
        round(x2 * scale_x),
        round(y2 * scale_y)
    )

    return image.crop(coords)


# Home Page
@app.get("/", include_in_schema=False)
async def home():

    html_file = BASE_DIR / "static" / "index.html"

    if not html_file.exists():

        raise HTTPException(
            status_code=500,
            detail="static/index.html file not found"
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
        "service": "DK Ayushman PVC Print"
    }


# Ayushman Card Print API
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

            raise ValueError("PDF page not found")

        page = doc[0]

        # Check Sample PDF Layout
        if (
            abs(page.rect.width - 850) > 2
            or abs(page.rect.height - 300) > 2
        ):
            raise ValueError(
                "PDF layout does not match the supported sample template"
            )

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

        # Calculate Rendering Scale
        scale_x = pix.width / page.rect.width
        scale_y = pix.height / page.rect.height

        # Extract Front and Back
        front = crop_card(
            image,
            FRONT_BOX,
            scale_x,
            scale_y
        )

        back = crop_card(
            image,
            BACK_BOX,
            scale_x,
            scale_y
        )

        # Rounded Corners
        front = rounded_card(front)
        back = rounded_card(back)

        # Create A4 PDF
        output = fitz.open()

        pdf_page = output.new_page(
            width=A4_WIDTH,
            height=A4_HEIGHT
        )

        # Calculate Horizontal Position
        total_width = (
            CARD_WIDTH * 2 + GAP
        )

        start_x = (
            A4_WIDTH - total_width
        ) / 2

        # Cards at Top of A4 Page
        start_y = TOP_MARGIN

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
                CARD_WIDTH + GAP
            )

            rect = fitz.Rect(
                x,
                start_y,
                x + CARD_WIDTH,
                start_y + CARD_HEIGHT
            )

            pdf_page.insert_image(
                rect,
                stream=buffer.getvalue(),
                keep_proportion=False
            )

            buffer.close()

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
                'attachment; filename="DK_Ayushman_PVC_Card.pdf"'
            }
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    finally:

        if doc is not None:
            doc.close()

        if output is not None:
            output.close()

        await file.close()
