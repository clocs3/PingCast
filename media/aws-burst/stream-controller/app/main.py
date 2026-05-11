from fastapi import FastAPI
from app.api import rtmp

try:
    from app.observability import setup_observability
except Exception:
    def setup_observability(app: FastAPI) -> None:
        return

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except Exception:
    Instrumentator = None

app = FastAPI()
setup_observability(app)
if Instrumentator is not None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
app.include_router(rtmp.router)


@app.get("/health")
def health():
    return {"status": "ok"}
