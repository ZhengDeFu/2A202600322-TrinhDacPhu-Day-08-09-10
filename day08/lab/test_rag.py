#!/usr/bin/env python3
"""
Test script để kiểm tra RAG pipeline nhanh
"""
from rag_answer import rag_answer

# Test queries
test_queries = [
    "SLA xử lý ticket P1 là bao lâu?",
    "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?",
    "Ai phải phê duyệt để cấp quyền Level 3?",
]

print("="*70)
print("Test RAG Pipeline - Sprint 2")
print("="*70)

for query in test_queries:
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print('='*70)
    
    try:
        result = rag_answer(query, retrieval_mode="dense", verbose=True)
        print(f"\n✓ Answer: {result['answer']}")
        print(f"✓ Sources: {result['sources']}")
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()
