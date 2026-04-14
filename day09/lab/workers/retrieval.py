"""
workers/retrieval.py — Retrieval Worker (Refactored)

Responsibilities:
    - Retrieve relevant chunks from ChromaDB
    - Return chunks + sources
    - Log worker IO
    - Handle errors safely

Run standalone:
    python workers/retrieval.py
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

WORKER_NAME = "retrieval_worker"

DEFAULT_TOP_K = 5  # Tăng từ 3 lên 5 để có nhiều context hơn

CHROMA_PATH = "./chroma_db"  # Fixed path for day09

COLLECTION_NAME = "day09_docs"  # Fixed collection name

EMBED_MODEL_NAME = "text-embedding-3-small"  # OpenAI embedding


# Global cache
_embed_fn = None
_collection = None


# ============================================================
# EMBEDDING
# ============================================================

def _get_embedding_fn():

    global _embed_fn

    if _embed_fn is not None:
        return _embed_fn

    # Priority 1: OpenAI (for Day 09)
    try:
        from openai import OpenAI
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env")
        
        client = OpenAI(api_key=api_key)

        def embed(text: str):
            response = client.embeddings.create(
                input=text,
                model=EMBED_MODEL_NAME
            )
            return response.data[0].embedding

        _embed_fn = embed

        print(f"✅ Loaded OpenAI embedding: {EMBED_MODEL_NAME}")

        return _embed_fn

    except Exception as e:
        print(f"⚠️  OpenAI embedding failed: {e}")
        print("   Falling back to sentence-transformers...")

    # Priority 2: Sentence Transformers (fallback)
    try:

        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")

        def embed(text: str):

            vec = model.encode(
                [text]
            )[0]

            return vec.tolist()

        _embed_fn = embed

        print(f"✅ Loaded sentence-transformers: all-MiniLM-L6-v2")

        return _embed_fn

    except Exception as e:

        raise RuntimeError(
            "Both OpenAI and sentence-transformers failed.\n"
            f"Error: {e}"
        )


# ============================================================
# CHROMA COLLECTION
# ============================================================

def _get_collection():

    global _collection

    if _collection is not None:
        return _collection

    try:

        import chromadb

        client = chromadb.PersistentClient(
            path=CHROMA_PATH
        )

        _collection = client.get_collection(
            COLLECTION_NAME
        )

        count = _collection.count()

        if count == 0:

            raise RuntimeError(
                f"Collection '{COLLECTION_NAME}' "
                "exists but empty.\n"
                "Run indexing script first."
            )

        print(
            f"✅ Connected to collection "
            f"'{COLLECTION_NAME}' "
            f"(documents={count})"
        )

        return _collection

    except Exception as e:

        raise RuntimeError(
            f"Failed loading Chroma collection "
            f"'{COLLECTION_NAME}'.\n"
            "Run indexing first.\n"
            f"Error: {e}"
        )


# ============================================================
# DENSE RETRIEVAL
# ============================================================

def retrieve_dense(
    query: str,
    top_k: int = DEFAULT_TOP_K
):

    if not query.strip():
        return []

    embed = _get_embedding_fn()

    collection = _get_collection()

    query_embedding = embed(query)

    try:

        results = collection.query(

            query_embeddings=[
                query_embedding
            ],

            n_results=top_k,

            include=[
                "documents",
                "distances",
                "metadatas",
            ],
        )

        documents = results.get(
            "documents",
            [[]]
        )[0]

        distances = results.get(
            "distances",
            [[]]
        )[0]

        metadatas = results.get(
            "metadatas",
            [[]]
        )[0]

        chunks = []

        for doc, dist, meta in zip(
            documents,
            distances,
            metadatas
        ):

            meta = meta or {}

            score = max(
                0.0,
                1 - dist
            )

            chunks.append({

                "text": doc,

                "source":
                    meta.get(
                        "source",
                        "unknown"
                    ),

                "score":
                    round(score, 4),

                "metadata": meta,

            })

        # Sort highest score first
        chunks.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return chunks

    except Exception as e:

        print(
            f"⚠️ Chroma query failed: {e}"
        )

        return []


# ============================================================
# WORKER ENTRY POINT
# ============================================================

def run(state: dict) -> dict:

    task = state.get("task", "")

    top_k = state.get(
        "retrieval_top_k",
        DEFAULT_TOP_K
    )

    state.setdefault(
        "workers_called",
        []
    )

    state.setdefault(
        "history",
        []
    )

    state.setdefault(
        "worker_io_logs",
        []
    )

    state["workers_called"].append(
        WORKER_NAME
    )

    worker_io = {

        "worker": WORKER_NAME,

        "input": {
            "task": task,
            "top_k": top_k,
        },

        "output": None,

        "error": None,
    }

    try:

        start = time.time()

        chunks = retrieve_dense(
            task,
            top_k=top_k
        )

        latency_ms = int(
            (time.time() - start) * 1000
        )

        sources = list({

            c["source"]

            for c in chunks

        })

        state["retrieved_chunks"] = (
            chunks
        )

        state["retrieved_sources"] = (
            sources
        )

        worker_io["output"] = {

            "chunks_count":
                len(chunks),

            "sources":
                sources,

            "latency_ms":
                latency_ms,
        }

        state["history"].append(

            f"[{WORKER_NAME}] "
            f"{len(chunks)} chunks "
            f"in {latency_ms}ms"

        )

    except Exception as e:

        worker_io["error"] = {

            "code":
                "RETRIEVAL_FAILED",

            "reason":
                str(e),
        }

        state["retrieved_chunks"] = []
        state["retrieved_sources"] = []

        state["history"].append(

            f"[{WORKER_NAME}] ERROR {e}"

        )

    state["worker_io_logs"].append(
        worker_io
    )

    return state


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 50)
    print("Retrieval Worker Test")
    print("=" * 50)

    test_queries = [

        "SLA ticket P1 là bao lâu?",

        "Điều kiện được hoàn tiền là gì?",

        "Ai phê duyệt cấp quyền Level 3?",

    ]

    for q in test_queries:

        print(f"\n▶ Query: {q}")

        state = {

            "task": q,

            "retrieval_top_k": 3

        }

        result = run(state)

        chunks = result.get(
            "retrieved_chunks",
            []
        )

        print(
            f"Retrieved: {len(chunks)}"
        )

        for c in chunks[:2]:

            print(
                f" [{c['score']:.3f}] "
                f"{c['source']}: "
                f"{c['text'][:80]}..."
            )

        print(
            "Sources:",
            result.get(
                "retrieved_sources",
                []
            )
        )

    print("\n✅ retrieval_worker ready")