import os
import sys

import pytest

# Make the project root importable (agent.py, report.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def fake_groq_key(monkeypatch):
    # Tests never call Groq; the key only has to exist
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
