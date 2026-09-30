# URL Shortener Service (generated artifact)

Run locally:

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:

```
pytest -q
```

## Endpoints
- `POST /api/shorten` `{"url": "...", "custom_alias": "optional"}`
- `GET /{short_code}` -> 307 redirect (records a click)
- `GET /api/analytics/{short_code}` -> click stats
- `GET /api/health`
