"""Векторная база, используемая MCP-сервером."""
import hashlib, json, time

import numpy as np

from .. import config, llm

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

    def get(self, texts, allow_remote=True):
        missing = list(dict.fromkeys(t for t in texts if key_of(t) not in self.vectors))
        if missing and not allow_remote:
            raise RuntimeError(f"в кэше нет {len(missing)} embedding-векторов; загрузка базы не вызывает API автоматически")
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
        elif hasattr(client, "describe_index"):
            self._wait_index()
        for old in client.list_collections():
            if old.startswith(f"{PREFIX}{label}_") and old != self.name:
                client.drop_collection(old)

    def _load(self, chunks):
        vectors = self.vectors.get([emb_text(c) for c in chunks], allow_remote=False)
        self.client.create_collection(self.name, dimension=vectors.shape[1], metric_type="COSINE")
        rows = [{"id": i, "vector": v.tolist(), **c} for i, (c, v) in enumerate(zip(chunks, vectors))]
        for i in range(0, len(rows), 1000):
            self.client.insert(self.name, rows[i:i + 1000])
        self.client.flush(self.name)
        self._wait_index()

    def _wait_index(self, timeout=180):
        """Не считать базу готовой, пока индекс не закончил обработку строк."""
        for _ in range(timeout):
            info = self.client.describe_index(self.name, "vector")
            if info.get("state") == "Finished" and info.get("pending_index_rows", 0) == 0:
                return
            time.sleep(1)
        raise TimeoutError(f"индекс Milvus не готов за {timeout} секунд: {self.name}")

    def search(self, query, k=5, page=""):
        vector = self.vectors.get([query])[0].tolist()
        flt = f'page == "{page}"' if page else ""
        hits = self.client.search(self.name, data=[vector], limit=k, filter=flt, output_fields=["page", "section", "url", "text"])[0]
        return [{**h["entity"], "id": h["id"], "score": round(h["distance"], 4)} for h in hits]


def connect(exclude=(), label="full", attempts=5):
    """Подключить базу с ограниченными попытками и экспоненциальной задержкой."""
    from pymilvus import MilvusClient

    chunks = corpus_chunks(exclude)
    delays = (1, 2, 4, 8, 16)
    error = None
    for attempt in range(attempts):
        try:
            return KnowledgeBase(MilvusClient(uri=config.MILVUS_URI), chunks, label)
        except Exception as exc:
            error = exc
            if attempt + 1 == attempts:
                raise
            time.sleep(delays[min(attempt, len(delays) - 1)])
    raise RuntimeError("не удалось подключиться к Milvus") from error
