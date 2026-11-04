import os
from typing import Literal

from dotenv import load_dotenv
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from groq import Groq
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

load_dotenv()

COLLECTION = "docs"

client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"],
    port=6333,
)
embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
reranker = TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")
llm = Groq(api_key=os.environ["GROQ_API_KEY"])


class Citation(BaseModel):
    source: str
    page: int


class ExamQuestion(BaseModel):
    question: str
    answer: str


class Answer(BaseModel):
    from_document: str
    explanation: str
    key_points: list[str]
    exam_questions: list[ExamQuestion]
    found: bool
    confidence: Literal["high", "medium", "low"]
    citations: list[Citation]


SYSTEM = (
    "You are a friendly teacher helping students understand a topic and prepare for exams, "
    "using ONLY the provided passages from their PDF. "
    "Reply with ONLY a JSON object with these keys: "
    "from_document (string), explanation (string), key_points (list of strings), "
    "exam_questions (list of objects with 'question' and 'answer'), found (true or false), "
    "confidence ('high', 'medium' or 'low'), citations (list of objects with 'source' and 'page'). "
    "from_document: what the PDF itself says about the question, staying close to its own terms and examples; no outside facts. "
    "explanation: explain the same topic in simple, easy words as if teaching a first-year student, "
    "with a small real-life example or analogy when it helps, and explain technical terms. "
    "key_points: 3 to 6 short points to remember for the exam. "
    "exam_questions: 3 likely exam questions on this topic, each with a short model answer. "
    "citations: every source file and page you used. "
    "If the passages contain nothing relevant, return found=false, "
    "from_document='I could not find this in the documents', explanation='', "
    "key_points=[], exam_questions=[], citations=[] and confidence='low'."
)


def _filter(source):
    if not source:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))]
    )


def retrieve_baseline(question, k=5, source=None):
    vector = list(embedder.embed([question]))[0].tolist()
    res = client.query_points(
        COLLECTION,
        query=vector,
        limit=k,
        with_payload=True,
        query_filter=_filter(source),
    )
    return [
        {"source": p.payload["source"], "page": p.payload["page"], "text": p.payload["text"]}
        for p in res.points
    ]


def retrieve_reranked(question, k=5, candidates=20, source=None):
    found = retrieve_baseline(question, candidates, source)
    if not found:
        return []
    scores = list(reranker.rerank(question, [f["text"] for f in found]))
    ranked = sorted(zip(scores, found), key=lambda x: x[0], reverse=True)
    return [f for _, f in ranked[:k]]


def ask(question, source=None, limit=5):
    reranked = retrieve_reranked(question, limit, 20, source)
    plain = retrieve_baseline(question, 8, source)

    seen, passages = set(), []
    for p in reranked + plain:
        key = (p["source"], p["page"], p["text"][:40])
        if key not in seen:
            seen.add(key)
            passages.append(p)

    context = "\n\n".join(
        f"[{p['source']}, page {p['page']}]\n{p['text']}" for p in passages
    )

    resp = llm.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {question}\n\nReply in JSON."},
        ],
        response_format={"type": "json_object"},
    )
    answer = Answer.model_validate_json(resp.choices[0].message.content)

    unique = {(c.source, c.page): c for c in answer.citations}
    answer.citations = list(unique.values())
    return answer