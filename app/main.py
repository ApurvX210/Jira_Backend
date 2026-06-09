from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.routers import issues, sprints

app = FastAPI(
    title="Jira Backend",
    version="0.2.0",
    description="High-throughput project management API",
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(issues.router)
app.include_router(sprints.router)


# ── Global exception handlers ────────────────────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok"}
