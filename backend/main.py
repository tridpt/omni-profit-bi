"""
FastAPI Server for ProfitPulse BI — Omni-Channel Profit, RFM & Inventory Intelligence (Port 8045).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analytics import (
    get_inventory_abc_xyz,
    get_pnl_overview,
    get_rfm_cohort_and_optimizer,
    list_datasets,
    simulate_what_if,
)
from .database import delete_dataset, execute_safe_sql, get_connection, get_warehouse_schema_info
from .importer import build_executive_report_xlsx, build_import_template_xlsx, import_orders_file
from .predictive import get_predictive_and_stats_suite
from .seed_data import ensure_seed_data
from .sql_templates import get_sql_templates

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_seed_data(force_reseed=False)
    yield


app = FastAPI(
    title="ProfitPulse BI v2.0 — Omni-Channel Profit, RFM, Inventory & Predictive Decision Science",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class WhatIfRequest(BaseModel):
    dataset_id: str = "vn_fashion_omni"
    sku_code: str = "ALL"
    channel: str = "ALL"
    price_change_pct: float = Field(default=0.0, ge=-50.0, le=80.0)
    voucher_change_pts: float = Field(default=0.0, ge=-30.0, le=40.0)
    platform_fee_change_pts: float = Field(default=0.0, ge=-15.0, le=30.0)
    return_rate_change_pts: float = Field(default=0.0, ge=-20.0, le=35.0)
    cogs_change_pct: float = Field(default=0.0, ge=-40.0, le=60.0)
    ads_change_pct: float = Field(default=0.0, ge=-90.0, le=200.0)
    elasticity_override: float | None = Field(default=None, ge=-4.0, le=-0.1)


class SqlExecuteRequest(BaseModel):
    sql: str
    max_rows: int = Field(default=300, ge=1, le=1000)


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    datasets = list_datasets()
    return {
        "status": "ok",
        "service": "ProfitPulse BI",
        "port": 8045,
        "sqlite_version": sqlite3.sqlite_version,
        "datasets_count": len(datasets),
    }


@app.get("/api/datasets")
def api_datasets() -> dict[str, Any]:
    return {"datasets": list_datasets()}


@app.delete("/api/datasets/{dataset_id}")
def api_delete_dataset(dataset_id: str) -> dict[str, Any]:
    with get_connection(readonly=True) as conn:
        row = conn.execute(
            "SELECT is_builtin FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ dữ liệu.")
    if int(row["is_builtin"]) == 1:
        raise HTTPException(status_code=400, detail="Không thể xóa bộ dữ liệu mẫu mặc định của hệ thống.")
    delete_dataset(dataset_id)
    return {"deleted": dataset_id}


@app.get("/api/overview")
def api_overview(
    dataset_id: str = Query(default="vn_fashion_omni"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    channel: str | None = Query(default="ALL"),
) -> dict[str, Any]:
    return get_pnl_overview(dataset_id, start_date=start_date, end_date=end_date, channel=channel)


@app.get("/api/rfm-cohort")
def api_rfm_cohort(
    dataset_id: str = Query(default="vn_fashion_omni"),
    budget_vnd: float = Query(default=15_000_000, ge=500_000, le=500_000_000),
) -> dict[str, Any]:
    return get_rfm_cohort_and_optimizer(dataset_id=dataset_id, budget_vnd=budget_vnd)


@app.get("/api/inventory")
def api_inventory(dataset_id: str = Query(default="vn_fashion_omni")) -> dict[str, Any]:
    return get_inventory_abc_xyz(dataset_id=dataset_id)


@app.get("/api/predictive")
def api_predictive(
    dataset_id: str = Query(default="vn_fashion_omni"),
    channel: str = Query(default="ALL"),
) -> dict[str, Any]:
    return get_predictive_and_stats_suite(dataset_id=dataset_id, channel=channel)


@app.post("/api/simulate")
def api_simulate(req: WhatIfRequest) -> dict[str, Any]:
    return simulate_what_if(
        dataset_id=req.dataset_id,
        sku_code=req.sku_code,
        channel=req.channel,
        price_change_pct=req.price_change_pct,
        voucher_change_pts=req.voucher_change_pts,
        platform_fee_change_pts=req.platform_fee_change_pts,
        return_rate_change_pts=req.return_rate_change_pts,
        cogs_change_pct=req.cogs_change_pct,
        ads_change_pct=req.ads_change_pct,
        elasticity_override=req.elasticity_override,
    )


@app.get("/api/sql/workbench")
def api_sql_workbench(dataset_id: str = Query(default="vn_fashion_omni")) -> dict[str, Any]:
    return {
        "schema": get_warehouse_schema_info(dataset_id),
        "templates": get_sql_templates(dataset_id),
    }


@app.post("/api/sql/execute")
def api_sql_execute(req: SqlExecuteRequest) -> dict[str, Any]:
    try:
        return execute_safe_sql(req.sql, max_rows=req.max_rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import")
async def api_import_file(
    file: UploadFile = File(...),
    dataset_name: str = Form(default=""),
) -> dict[str, Any]:
    try:
        raw = await file.read()
        if len(raw) > 25 * 1024 * 1024:
            raise ValueError("Kích thước tệp vượt quá giới hạn 25MB.")
        return import_orders_file(raw, file.filename or "upload.xlsx", dataset_name or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không thể đọc tệp dữ liệu: {exc}") from exc


@app.get("/api/export/template.xlsx")
def api_export_template() -> Response:
    content = build_import_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ProfitPulse_Mau_Nhap_Don_Hang.xlsx"'},
    )


@app.get("/api/export/report.xlsx")
def api_export_report(dataset_id: str = Query(default="vn_fashion_omni")) -> Response:
    content = build_executive_report_xlsx(dataset_id)
    fname = f"Bao_Cao_Dieu_Hanh_{dataset_id}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return {"message": "Frontend is initializing..."}
    return FileResponse(str(index_file))
