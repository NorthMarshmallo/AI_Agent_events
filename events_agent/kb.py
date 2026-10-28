"""База знаний из этапа 2: страницы корпуса нарезаны по абзацам, векторы лежат в Milvus.

Векторы всех кусков уже посчитаны и лежат в data/embeddings_512.npz, поэтому загрузка базы бесплатна.
Имя коллекции содержит отпечаток кусков и модели эмбеддингов: если данные не менялись, база не перезаливается,
а коллекции той же базы со старым отпечатком удаляются, чтобы не копились в Milvus.
"""
import hashlib, json, time
import numpy as np
from pydantic import BaseModel, Field
from . import config, llm
from .tools import register

CACHE = config.DATA / "embeddings_512.npz"
PREFIX = "kb_"


def key_of(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def chunk_lines(page):
    chunks, section = [], ""
    for line in page["text"].splitlines():
        line = " ".join(line.split())
        if line.startswith("="):
            section = line.strip("= ")
        elif len(line) > 40:
            chunks.append({"page": page["page"], "section": section, "url": page["url"], "text": line})
    return chunks


def emb_text(chunk):
    return f"{chunk['page']}: {chunk['text']}"


class Vectors:
    def __init__(self, path=CACHE):
        self.path, self.vectors = path, {}
        if path.exists():
            z = np.load(path)
            self.vectors = {str(k): v.astype(np.float32) for k, v in zip(z["keys"], z["vectors"])}

    def get(self, texts):
        missing = list(dict.fromkeys(t for t in texts if key_of(t) not in self.vectors))
        for i in range(0, len(missing), 64):
            batch = missing[i:i + 64]
            for text, vector in zip(batch, llm.embed(batch)):
                self.vectors[key_of(text)] = np.asarray(vector, dtype=np.float32)
        vectors = np.stack([self.vectors[key_of(t)] for t in texts])
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def corpus_chunks(exclude=()):
    pages = [json.loads(line) for line in (config.DATA / "corpus_2026.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [c for p in pages if p["page"] not in exclude for c in chunk_lines(p)]


def collection_name(chunks, label):
    digest = hashlib.sha1(json.dumps([config.EMBED_MODEL, config.DIM, [emb_text(c) for c in chunks]], ensure_ascii=False).encode()).hexdigest()
    return f"{PREFIX}{label}_{digest[:12]}"


class KnowledgeBase:
    def __init__(self, client, chunks, label="full", vectors=None):
        self.client, self.vectors = client, vectors or Vectors()
        self.name = collection_name(chunks, label)
        if not client.has_collection(self.name):
            self._load(chunks)
        for old in client.list_collections():                 # старые версии той же базы
            if old.startswith(f"{PREFIX}{label}_") and old != self.name:
                client.drop_collection(old)

    def _load(self, chunks):
        vectors = self.vectors.get([emb_text(c) for c in chunks])
        self.client.create_collection(self.name, dimension=vectors.shape[1], metric_type="COSINE")
        rows = [{"id": i, "vector": v.tolist(), **c} for i, (c, v) in enumerate(zip(chunks, vectors))]
        for i in range(0, len(rows), 1000):
            self.client.insert(self.name, rows[i:i + 1000])
        self.client.flush(self.name)
        for _ in range(180):                                    # поиск до готовности индекса видит не все куски
            info = self.client.describe_index(self.name, "vector")
            if info.get("state") == "Finished" and info.get("pending_index_rows", 0) == 0:
                break
            time.sleep(1)

    def search(self, query, k=5, page=""):
        vector = self.vectors.get([query])[0].tolist()
        flt = f'page == "{page}"' if page else ""
        hits = self.client.search(self.name, data=[vector], limit=k, filter=flt, output_fields=["page", "section", "url", "text"])[0]
        return [{**h["entity"], "id": h["id"], "score": round(h["distance"], 4)} for h in hits]


class KBArgs(BaseModel):
    query: str = Field(description="short search query in English: names, dates, key terms of the event")
    page: str = Field(default="", description="optional exact page title to search within, for example '2026 in Japan'; empty means all pages")


def connect(exclude=(), label="full"):
    """label различает базы: full - весь корпус для работы, eval - без отложенных страниц для замера на golden set."""
    from pymilvus import MilvusClient                          # импорт здесь: без базы остальной пакет работает
    base = KnowledgeBase(MilvusClient(uri=config.MILVUS_URI), corpus_chunks(exclude), label)

    def knowledge_base(query: str, page: str = "") -> str:
        hits = base.search(query, page=page.replace('"', ""))
        if not hits:
            return "nothing found"
        return "\n".join(f"[{h['page']} / {h['section']}] {h['text']}" for h in hits)

    register(knowledge_base, KBArgs, "Searches the local knowledge base of 2026 events and returns the five closest facts with their page and section. "
                                     "The base holds English Wikipedia overview pages by country and field, such as '2026 in Japan', "
                                     "'2026 in sports', '2026 in science'")
    return base
