from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.websocket import manager
from app.routers import board, comments, issues, notifications, projects, sprints, users, watchers

app = FastAPI(
    title="Jira Backend",
    version="0.4.0",
    description="High-throughput project management API",
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(projects.router)
app.include_router(users.router)
app.include_router(issues.router)
app.include_router(sprints.router)
app.include_router(comments.router)
app.include_router(board.router)
app.include_router(watchers.router)
app.include_router(notifications.router)


# ── Global exception handlers ────────────────────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


# ── WebSocket (presence tracking + event replay) ─────────────────────────────
@app.websocket("/ws/projects/{project_id}")
async def ws_project(
    websocket: WebSocket,
    project_id: str,
    user_id: str = Query(...),
    last_seq: int | None = Query(default=None),
) -> None:
    await manager.connect(project_id, user_id, websocket)
    try:
        # Replay missed events if the client is reconnecting
        if last_seq is not None:
            await manager.replay(websocket, project_id, last_seq)

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(project_id, user_id, websocket)


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok"}
