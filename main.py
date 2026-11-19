
import io
import fitz
from PIL import Image, ImageDraw
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI(title="DK Jan Suvidha Kendra - Ayushman Card Print")

# A4 dimensions in points
A4_WIDTH = 595.28
A4_HEIGHT = 841.89

# Sample PDF के अनुसार Front और Back की crop position
FRONT_BOX = (0.098, 0.376, 0.391, 0.990)
BACK_BOX  = (0.423, 0.376, 0.714, 0.990)

def rounded_card(img, radius=22):
    img = img.convert("RGB")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, img.width - 1, img.height - 1),
        radius=radius,
        fill=255
    )
    result = Image.new("RGBA", img.size, (255, 255, 255, 0))
    result.paste(img, (0, 0))
    result.putalpha(mask)
    return result

def crop_card(image, box):
    w, h = image.size

    coords = (
        int(w * box[0]),
        int(h * box[1]),
        int(w * box[2]),
        int(h * box[3])
    )

    return image.crop(coords)

@app.post("/api/ayushman-a4")
async def ayushman_print(file: UploadFile = File(...)):

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are allowed")

    data = await file.read()

    try:
        doc = fitz.open(stream=data, filetype="pdf")

        if len(doc) < 1:
            raise ValueError("Empty PDF")

        page = doc[0]

        # High quality PDF rendering
        pix = page.get_pixmap(
            matrix=fitz.Matrix(3, 3),
            alpha=False
        )

        image = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        # Front and Back crop
        front = crop_card(image, FRONT_BOX)
        back = crop_card(image, BACK_BOX)

        front = rounded_card(front)
        back = rounded_card(back)

        # Create A4 PDF
        output = fitz.open()
        pdf_page = output.new_page(
            width=A4_WIDTH,
            height=A4_HEIGHT
        )

        # Card dimensions in points
        card_width = 248
        card_height = 248 * (front.height / front.width)

        gap = 10
        total_width = card_width * 2 + gap

        start_x = (A4_WIDTH - total_width) / 2
        start_y = (A4_HEIGHT - card_height) / 2

        cards = [front, back]

        for i, card in enumerate(cards):

            buffer = io.BytesIO()
            card.save(buffer, format="PNG")
            buffer.seek(0)

            x = start_x + i * (card_width + gap)

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

        result = output.tobytes(
            garbage=4,
            deflate=True
        )

        output.close()
        doc.close()

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
