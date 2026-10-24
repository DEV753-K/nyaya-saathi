# Nyaya Saathi

Backend (FastAPI) + frontend (static page served by the backend) in one folder.

## Run locally
    pip install -r requirements.txt
    uvicorn app.main:app --reload
Open http://127.0.0.1:8000  (API docs: /docs)

## Optional: smarter understanding with an LLM
    set ANTHROPIC_API_KEY=your_key        (Windows)
    export ANTHROPIC_API_KEY=your_key     (Mac/Linux)
Without a key, the built-in rule-based parser is used.

## Deploy on Render (free)
1. Push this folder to GitHub.
2. Render > New > Web Service > pick the repo.
3. Build command:  pip install -r requirements.txt
4. Start command:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
5. (Optional) add ANTHROPIC_API_KEY under Environment.
You get one public link that serves both the website and the API.
