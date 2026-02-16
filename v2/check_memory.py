from dotenv import load_dotenv
from pymilvus import MilvusClient
from langchain_openai import OpenAIEmbeddings

load_dotenv()

# Docker Compose로 띄운 Milvus 연결
milvus_client = MilvusClient(uri="http://127.0.0.1:19530")
COLLECTION_NAME = "editor_feedback"

# 1. 총 데이터 개수 확인
res = milvus_client.query(
    collection_name=COLLECTION_NAME,
    output_fields=["count(*)"]
)
print(f"📊 저장된 기억 개수: {res}")

# 2. 최근 저장된 피드백 3개 확인
results = milvus_client.query(
    collection_name=COLLECTION_NAME,
    filter="id >= 0", # 모든 데이터 조회
    output_fields=["text", "topic", "timestamp"],
    limit=3
)

print("\n📝 최근 저장된 피드백 내용:")
for r in results:
    print(f"- 주제: {r['topic']}")
    print(f"- 내용: {r['text'][:50]}...") # 앞부분만 출력
    print("-" * 30)