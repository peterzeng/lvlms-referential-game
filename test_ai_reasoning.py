import os
import json
import sqlite3
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Start a game
response = client.post("/api/game/start", json={
    "session_id": "test_reasoning_1",
    "round_number": 1,
    "director_model": "gpt-4o-mini",
    "matcher_model": "gpt-4o-mini",
    "model": "gpt-4o-mini"
})
print("Start Game:", response.json())

# Play one turn
response = client.post("/api/game/turn", json={"session_id": "test_reasoning_1"})
print("Play Turn:", response.json())

# Export session
response = client.get("/api/game/export?session_id=test_reasoning_1")
data = response.json()
print("Export Data:", json.dumps(data[0].get("ai_reasoning_log"), indent=2)[:500])

