"""FastAPI server — run the NSE agent from a browser.

Start with:
    uvicorn nse_agent.server:app --host 0.0.0.0 --port 8000
or:
    python -m nse_agent.server

Then open http://localhost:8000
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .agent import NSEAgent
from .config import DISCLAIMER, AgentConfig

app = FastAPI(title="NSE Stock Analysis Agent")

STATIC_DIR = Path(__file__).parent / "static"

# One scan at a time; results cached for the dashboard to poll.
_lock = threading.Lock()
_state: dict = {"status": "idle", "report": None, "error": None,
                "started_at": None, "finished_at": None, "params": None}


class ScanRequest(BaseModel):
    mode: str = "both"            # invest | intraday | both
    capital: float = 100_000
    top: int = 10
    limit: int | None = None      # scan only first N symbols (faster)


def _run_scan(req: ScanRequest) -> None:
    global _state
    try:
        cfg = AgentConfig(capital=req.capital, top_n=req.top, universe_size=req.limit)
        report = NSEAgent(cfg).run(mode=req.mode)
        _state.update(status="done", report=report, finished_at=time.time())
    except Exception as e:  # noqa: BLE001 — surface any failure to the UI
        traceback.print_exc()
        _state.update(status="error", error=str(e), finished_at=time.time())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/scan")
def start_scan(req: ScanRequest):
    if req.mode not in ("invest", "intraday", "both"):
        return JSONResponse({"error": "mode must be invest|intraday|both"}, status_code=400)
    with _lock:
        if _state["status"] == "running":
            return JSONResponse({"error": "a scan is already running"}, status_code=409)
        _state.update(status="running", report=None, error=None,
                      started_at=time.time(), finished_at=None,
                      params=req.model_dump())
    threading.Thread(target=_run_scan, args=(req,), daemon=True).start()
    return {"status": "started", "params": req.model_dump()}


@app.get("/api/status")
def status():
    out = dict(_state)
    out["disclaimer"] = DISCLAIMER
    if out["status"] == "running" and out["started_at"]:
        out["elapsed_sec"] = round(time.time() - out["started_at"], 1)
    return out


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
