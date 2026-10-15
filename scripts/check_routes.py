from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
for path in ("/api/v1/workflow-templates", "/api/v1/tasks/00000000-0000-0000-0000-000000000000/workflow"):
    r = client.get(path)
    print(path, "->", r.status_code, r.json() if r.status_code != 404 else "NOT FOUND")
