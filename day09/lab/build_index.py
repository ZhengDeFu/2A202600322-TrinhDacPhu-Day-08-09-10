"""
build_index.py — Improved Indexing for Day 09
Cải thiện chunking và metadata để tăng retrieval quality.

Chạy:
    python3 build_index.py
"""

import os
import re
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Config
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "day09_docs"
DOCS_DIR = "./data/docs"
EMBED_MODEL = "text-embedding-3-small"  # OpenAI embedding model

# Chunking config
CHUNK_SIZE = 300  # characters per chunk
CHUNK_OVERLAP = 50  # overlap between chunks


def smart_chunk_document(content: str, source: str) -> List[Dict]:
    """
    Chunking thông minh với overlap và metadata.
    
    Strategy:
    1. Tách theo sections (headers, numbered lists)
    2. Nếu section quá dài, chia nhỏ với overlap
    3. Thêm metadata: section name, keywords, doc type
    """
    chunks = []
    
    # Detect document type từ filename
    doc_type = "unknown"
    if "sla" in source.lower():
        doc_type = "SLA"
    elif "policy" in source.lower() or "refund" in source.lower():
        doc_type = "Policy"
    elif "access" in source.lower():
        doc_type = "Access Control"
    elif "faq" in source.lower() or "helpdesk" in source.lower():
        doc_type = "IT Helpdesk"
    elif "hr" in source.lower() or "leave" in source.lower():
        doc_type = "HR Policy"
    
    # Split theo sections (headers hoặc numbered items)
    # Pattern: "## Header" hoặc "1. Item" hoặc "Điều 1:"
    section_pattern = r'(?:^|\n)(?:#{1,3}\s+|(?:\d+\.|\*)\s+|Điều\s+\d+:)'
    sections = re.split(section_pattern, content)
    
    # Lấy section headers
    headers = re.findall(section_pattern, content)
    
    for i, section in enumerate(sections):
        section = section.strip()
        if not section or len(section) < 20:
            continue
        
        # Lấy section name từ header
        section_name = headers[i].strip() if i < len(headers) else "Introduction"
        
        # Nếu section ngắn, giữ nguyên
        if len(section) <= CHUNK_SIZE:
            chunks.append({
                "text": section,
                "metadata": {
                    "source": source,
                    "doc_type": doc_type,
                    "section": section_name,
                    "chunk_index": len(chunks),
                }
            })
        else:
            # Section dài → chia nhỏ với overlap
            start = 0
            chunk_idx = 0
            while start < len(section):
                end = start + CHUNK_SIZE
                chunk_text = section[start:end]
                
                # Tìm boundary tốt (kết thúc câu)
                if end < len(section):
                    # Tìm dấu chấm gần nhất
                    last_period = chunk_text.rfind('.')
                    if last_period > CHUNK_SIZE * 0.7:  # Ít nhất 70% chunk
                        end = start + last_period + 1
                        chunk_text = section[start:end]
                
                chunks.append({
                    "text": chunk_text.strip(),
                    "metadata": {
                        "source": source,
                        "doc_type": doc_type,
                        "section": section_name,
                        "chunk_index": len(chunks),
                        "is_continuation": chunk_idx > 0,
                    }
                })
                
                # Move với overlap
                start = end - CHUNK_OVERLAP
                chunk_idx += 1
    
    return chunks


def extract_keywords(text: str) -> List[str]:
    """Extract keywords từ text để improve search."""
    keywords = []
    
    # Common domain keywords
    keyword_patterns = {
        "SLA": ["P1", "P2", "escalation", "response time", "resolution", "phản hồi", "xử lý"],
        "Policy": ["hoàn tiền", "refund", "flash sale", "exception", "ngoại lệ", "điều kiện"],
        "Access": ["Level 1", "Level 2", "Level 3", "approval", "phê duyệt", "quyền", "access"],
        "Ticket": ["ticket", "incident", "on-call", "PagerDuty", "Slack"],
    }
    
    text_lower = text.lower()
    for category, patterns in keyword_patterns.items():
        if any(p.lower() in text_lower for p in patterns):
            keywords.append(category)
    
    return keywords


def get_embeddings(texts: List[str], client: OpenAI) -> List[List[float]]:
    """Get embeddings from OpenAI API."""
    response = client.embeddings.create(
        input=texts,
        model=EMBED_MODEL
    )
    return [item.embedding for item in response.data]


def build_index():
    """Build ChromaDB index với improved chunking."""
    print("=" * 60)
    print("Building Improved Index for Day 09")
    print("=" * 60)
    
    # Initialize OpenAI client
    print(f"\n📦 Using OpenAI embedding model: {EMBED_MODEL}...")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Initialize ChromaDB
    import chromadb
    print(f"🗄️  Initializing ChromaDB at {CHROMA_PATH}...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    # Delete old collection
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        print(f"🗑️  Deleted old collection '{COLLECTION_NAME}'")
    except:
        pass
    
    # Create new collection
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"✅ Created collection '{COLLECTION_NAME}'")
    
    # Process documents
    all_chunks = []
    doc_stats = {}
    
    for filename in sorted(os.listdir(DOCS_DIR)):
        if not filename.endswith('.txt'):
            continue
        
        filepath = os.path.join(DOCS_DIR, filename)
        print(f"\n📄 Processing: {filename}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Smart chunking
        chunks = smart_chunk_document(content, filename)
        
        # Add keywords to metadata
        for chunk in chunks:
            keywords = extract_keywords(chunk["text"])
            chunk["metadata"]["keywords"] = ",".join(keywords)
        
        all_chunks.extend(chunks)
        doc_stats[filename] = len(chunks)
        print(f"   → {len(chunks)} chunks created")
    
    # Embed and add to ChromaDB
    print(f"\n🔢 Embedding {len(all_chunks)} chunks with OpenAI...")
    
    batch_size = 100  # OpenAI allows up to 2048 inputs per request
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        
        texts = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]
        ids = [f"chunk_{i+j}" for j in range(len(batch))]
        
        # Embed using OpenAI
        embeddings = get_embeddings(texts, client)
        
        # Add to collection
        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"   Batch {i//batch_size + 1}/{(len(all_chunks)-1)//batch_size + 1} added ({len(batch)} chunks)")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Index Build Complete!")
    print("=" * 60)
    print(f"Total chunks: {len(all_chunks)}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Chunk size: {CHUNK_SIZE} chars (overlap: {CHUNK_OVERLAP})")
    print("\nPer-document stats:")
    for doc, count in doc_stats.items():
        print(f"  • {doc}: {count} chunks")
    
    # Test query
    print("\n🧪 Testing retrieval...")
    test_query = "SLA ticket P1 là bao lâu?"
    query_embedding = get_embeddings([test_query], client)[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3,
        include=["documents", "distances", "metadatas"]
    )
    
    print(f"\nTest query: '{test_query}'")
    print("Top 3 results:")
    for i, (doc, dist, meta) in enumerate(zip(
        results["documents"][0],
        results["distances"][0],
        results["metadatas"][0]
    ), 1):
        score = 1 - dist
        print(f"\n[{i}] Score: {score:.3f} | {meta.get('source')} | {meta.get('section')}")
        print(f"    {doc[:100]}...")


if __name__ == "__main__":
    build_index()
