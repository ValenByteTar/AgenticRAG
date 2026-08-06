"""Quick Ollama connectivity check."""
import requests

try:
    r = requests.get("http://localhost:11434/api/tags", timeout=10)
    models = r.json().get("models", [])
    print(f"Ollama: {len(models)} models available")
    for m in models:
        if "granite" in m["name"].lower():
            print(f"  {m['name']}")
except Exception as e:
    print(f"Ollama error: {e}")
