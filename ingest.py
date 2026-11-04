import io
import uuid

from pypdf import PdfReader
from qdrant_client import models

from core import client, embedder, COLLECTION

CHUNK_SIZE = 800
OVERLAP = 150
MAX_PAGES = 150


def split_text(text):
    clean = " ".join(text.split())
    chunks = []
    for i in range(0, len(clean), CHUNK_SIZE - OVERLAP):
        piece = clean[i : i + CHUNK_SIZE]
        if len(piece) > 100:
            chunks.append(piece)
    return chunks


def ingest_pdf(data: bytes, filename: str):
    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages[:MAX_PAGES]]

    try:
        client.create_payload_index(
            COLLECTION,
            field_name="source",
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )
    except Exception:
        pass

    client.delete(
        COLLECTION,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source", match=models.MatchValue(value=filename)
                    )
                ]
            )
        ),
        wait=True,
    )

    items = []
    for page_no, text in enumerate(pages, start=1):
        for chunk in split_text(text):
            items.append((page_no, chunk))

    if not items:
        return {"filename": filename, "pages": len(pages), "chunks": 0}

    vectors = list(embedder.embed([c for _, c in items]))
    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=v.tolist(),
            payload={"text": c, "source": filename, "page": p, "chunk": i},
        )
        for i, ((p, c), v) in enumerate(zip(items, vectors))
    ]
    for start in range(0, len(points), 50):
        client.upsert(COLLECTION, points=points[start : start + 50], wait=True)

    return {"filename": filename, "pages": len(pages), "chunks": len(points)}