from fastapi import FastAPI

SERVICE_NAME = "xdr_rico"

app = FastAPI(title="xdr_rico", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
