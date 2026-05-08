from fastapi import FastAPI

SERVICE_NAME = "siem_kowalski"

app = FastAPI(title="siem_kowalski", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
