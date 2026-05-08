from fastapi import FastAPI

SERVICE_NAME = "soar_skipper"

app = FastAPI(title="soar_skipper", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
