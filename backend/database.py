"""
SQLite Analytical Data Warehouse & Safe Read-Only SQL Sandbox
for ProfitPulse BI (Port 8045).
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "profitpulse_warehouse.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'VND',
    created_at TEXT NOT NULL,
    is_builtin INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS skus (
    dataset_id TEXT NOT NULL,
    sku_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    list_price REAL NOT NULL,
    unit_cogs REAL NOT NULL,
    packaging_cost REAL NOT NULL DEFAULT 0,
    current_stock INTEGER NOT NULL DEFAULT 0,
    lead_time_days INTEGER NOT NULL DEFAULT 7,
    min_order_qty INTEGER NOT NULL DEFAULT 20,
    price_elasticity REAL NOT NULL DEFAULT -1.35,
    PRIMARY KEY (dataset_id, sku_code)
);

CREATE TABLE IF NOT EXISTS customers (
    dataset_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    phone_masked TEXT NOT NULL,
    city TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,
    acquisition_cost REAL NOT NULL DEFAULT 0,
    first_order_date TEXT NOT NULL,
    PRIMARY KEY (dataset_id, customer_id)
);

CREATE TABLE IF NOT EXISTS orders (
    dataset_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    order_month TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL, -- COMPLETED | RETURNED | CANCELLED
    gross_amount REAL NOT NULL,
    seller_voucher REAL NOT NULL DEFAULT 0,
    platform_subsidy REAL NOT NULL DEFAULT 0,
    shipping_fee_seller REAL NOT NULL DEFAULT 0,
    return_logistics_fee REAL NOT NULL DEFAULT 0,
    platform_fee REAL NOT NULL DEFAULT 0,
    payment_fee REAL NOT NULL DEFAULT 0,
    affiliate_fee REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, order_id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    sku_code TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_list_price REAL NOT NULL,
    item_gross REAL NOT NULL,
    item_seller_discount REAL NOT NULL DEFAULT 0,
    item_net_revenue REAL NOT NULL DEFAULT 0,
    item_cogs REAL NOT NULL DEFAULT 0,
    item_packaging_cost REAL NOT NULL DEFAULT 0,
    item_platform_fee REAL NOT NULL DEFAULT 0,
    item_payment_fee REAL NOT NULL DEFAULT 0,
    item_affiliate_fee REAL NOT NULL DEFAULT 0,
    item_shipping_seller REAL NOT NULL DEFAULT 0,
    item_return_loss REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS marketing_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    spend_date TEXT NOT NULL,
    spend_month TEXT NOT NULL,
    channel TEXT NOT NULL,
    sku_code TEXT NOT NULL,
    ad_spend REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_orders_ds_date ON orders(dataset_id, order_date);
CREATE INDEX IF NOT EXISTS idx_orders_ds_month ON orders(dataset_id, order_month);
CREATE INDEX IF NOT EXISTS idx_orders_ds_cust ON orders(dataset_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_ds_chan ON orders(dataset_id, channel);
CREATE INDEX IF NOT EXISTS idx_items_ds_order ON order_items(dataset_id, order_id);
CREATE INDEX IF NOT EXISTS idx_items_ds_order_sku ON order_items(dataset_id, order_id, sku_code);
CREATE INDEX IF NOT EXISTS idx_items_ds_sku ON order_items(dataset_id, sku_code);
CREATE INDEX IF NOT EXISTS idx_mkt_ds_date ON marketing_daily(dataset_id, spend_date);
CREATE INDEX IF NOT EXISTS idx_mkt_ds_sku ON marketing_daily(dataset_id, sku_code);

DROP VIEW IF EXISTS vw_order_item_pnl;
CREATE VIEW vw_order_item_pnl AS
SELECT
    oi.dataset_id,
    o.order_id,
    o.order_date,
    o.order_month,
    o.channel,
    o.customer_id,
    o.status,
    oi.sku_code,
    s.product_name,
    s.category,
    oi.quantity,
    oi.item_gross,
    oi.item_seller_discount,
    oi.item_net_revenue,
    oi.item_cogs,
    oi.item_packaging_cost,
    oi.item_platform_fee,
    oi.item_payment_fee,
    oi.item_affiliate_fee,
    oi.item_shipping_seller,
    oi.item_return_loss,
    (
        oi.item_net_revenue
        - oi.item_cogs
        - oi.item_packaging_cost
        - oi.item_platform_fee
        - oi.item_payment_fee
        - oi.item_affiliate_fee
        - oi.item_shipping_seller
        - oi.item_return_loss
    ) AS contribution_profit_before_ads
FROM order_items oi
JOIN orders o
  ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
LEFT JOIN skus s
  ON s.dataset_id = oi.dataset_id AND s.sku_code = oi.sku_code;
"""

FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|VACUUM|REINDEX|PRAGMA)\b",
    re.IGNORECASE,
)


def get_connection(readonly: bool = False) -> sqlite3.Connection:
    """Return a SQLite connection (read-only URI mode when requested)."""
    if readonly and DB_PATH.exists():
        uri = f"file:{DB_PATH.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create warehouse tables, indexes, and analytical views."""
    with get_connection(readonly=False) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def delete_dataset(dataset_id: str) -> None:
    """Remove all records belonging to a specific dataset_id."""
    with get_connection(readonly=False) as conn:
        for table in ("order_items", "orders", "marketing_daily", "customers", "skus", "datasets"):
            conn.execute(f"DELETE FROM {table} WHERE dataset_id = ?", (dataset_id,))
        conn.commit()


def execute_safe_sql(
    sql_query: str,
    params: dict[str, Any] | None = None,
    max_rows: int = 500,
    timeout_sec: float = 4.0,
) -> dict[str, Any]:
    """
    Execute a user-provided SELECT/WITH analytical SQL query safely in read-only mode.
    Enforces statement validation, CPU timeout via progress handler, and row cap.
    """
    cleaned = (sql_query or "").strip()
    if not cleaned:
        raise ValueError("Câu lệnh SQL không được để trống.")

    # Strip SQL comments before checking keywords
    no_comments = re.sub(r"--[^\n]*", " ", cleaned)
    no_comments = re.sub(r"/\*.*?\*/", " ", no_comments, flags=re.DOTALL).strip()
    # Allow a single trailing semicolon
    statements = [s.strip() for s in no_comments.split(";") if s.strip()]
    if len(statements) != 1:
        raise ValueError("Chỉ cho phép thực thi duy nhất 1 câu truy vấn SELECT / WITH mỗi lần.")

    stmt = statements[0]
    if not re.match(r"^(SELECT|WITH|EXPLAIN)\b", stmt, re.IGNORECASE):
        raise ValueError("Phòng Lab SQL chỉ cho phép truy vấn đọc dữ liệu (SELECT / WITH CTE / EXPLAIN).")

    if FORBIDDEN_SQL_PATTERN.search(stmt):
        raise ValueError("Phát hiện từ khóa thay đổi cấu trúc/dữ liệu bị chặn trong chế độ Read-Only Sandbox.")

    started = time.perf_counter()
    deadline = started + timeout_sec

    conn = get_connection(readonly=True)
    try:
        def _progress_guard() -> int:
            return 1 if time.perf_counter() > deadline else 0

        conn.set_progress_handler(_progress_guard, 5000)
        cur = conn.execute(cleaned, params or {})
        columns = [desc[0] for desc in (cur.description or [])]
        fetched = cur.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows_raw = fetched[:max_rows]
        rows = [dict(zip(columns, row)) for row in rows_raw]
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "max_rows": max_rows,
            "elapsed_ms": elapsed_ms,
        }
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            raise ValueError(f"Truy vấn vượt quá giới hạn thời gian ({timeout_sec}s). Hãy thêm điều kiện lọc hoặc LIMIT.") from exc
        raise ValueError(f"Lỗi cú pháp SQL: {exc}") from exc
    finally:
        conn.close()


def get_warehouse_schema_info(dataset_id: str) -> list[dict[str, Any]]:
    """Return metadata & row counts for all analytical tables/views for the SQL Workbench."""
    objects = [
        ("orders", "TABLE", "Đơn hàng đa kênh (ngày đặt, kênh bán, trạng thái COMPLETED/RETURNED/CANCELLED, voucher, phí sàn)"),
        ("order_items", "TABLE", "Chi tiết từng dòng sản phẩm trong đơn (số lượng, doanh thu thuần, giá vốn, phí sàn, thiệt hại hoàn đơn)"),
        ("skus", "TABLE", "Danh mục mã hàng SKU (giá niêm yết, giá vốn COGS, phí đóng gói, tồn kho hiện tại, lead time nhập hàng)"),
        ("customers", "TABLE", "Hồ sơ khách hàng (tỉnh thành, kênh thu hút ban đầu, chi phí thu hút CAC, ngày mua đầu tiên)"),
        ("marketing_daily", "TABLE", "Chi phí chạy quảng cáo Ads theo ngày, kênh và mã hàng SKU (spend, impressions, clicks)"),
        ("vw_order_item_pnl", "VIEW", "View tổng hợp sẵn P&L từng dòng sản phẩm kèm lợi nhuận gộp trước Ads"),
    ]
    result = []
    with get_connection(readonly=True) as conn:
        for obj_name, obj_type, desc in objects:
            cols_cur = conn.execute(f"PRAGMA table_info({obj_name})").fetchall()
            cols = [{"name": r["name"], "type": r["type"] or "NUMERIC"} for r in cols_cur]
            cnt_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM {obj_name} WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            result.append(
                {
                    "name": obj_name,
                    "type": obj_type,
                    "description": desc,
                    "row_count": int(cnt_row["cnt"]) if cnt_row else 0,
                    "columns": cols,
                }
            )
    return result
