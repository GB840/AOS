import sys
import pytest
sys.path.insert(0, 'd:/AOS')

print('Testing Qdrant connection...')
pytest.importorskip("qdrant_client")
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Distance, VectorParams

try:
    client = QdrantClient(url='http://localhost:6335', timeout=2)
    collections = client.get_collections()
    print('Existing collections:', [c.name for c in collections.collections])
except Exception:
    pytest.skip("Qdrant server not available at localhost:6335", allow_module_level=True)

client.create_collection(
    collection_name='test_graphrag',
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)
print('Created collection: test_graphrag')

test_vector = [0.1] * 384
point = PointStruct(
    id='test-1',
    vector=test_vector,
    payload={'name': '测试实体', 'type': 'entity'}
)
client.upsert(collection_name='test_graphrag', points=[point])
print('Added test point')

results = client.search(
    collection_name='test_graphrag',
    query_vector=test_vector,
    limit=1
)
print('Search result:', results[0].payload)

client.delete_collection(collection_name='test_graphrag')
print('Deleted test collection')

print('Qdrant tests passed!')