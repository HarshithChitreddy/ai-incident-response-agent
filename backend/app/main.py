from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title=get_settings().app_name)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
