"""
Real-World CSV / Excel (.xlsx) Smart Importer, Dirty-Data Cleaner,
Sample Template Builder & Multi-Sheet Executive Report Exporter.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .analytics import get_inventory_abc_xyz, get_pnl_overview, get_rfm_cohort_and_optimizer
from .database import delete_dataset, get_connection


COLUMN_SYNONYMS: dict[str, list[str]] = {
    "order_id": ["orderid", "madonhang", "madon", "sohoadon", "iddonhang", "orderno", "macode"],
    "order_date": ["orderdate", "ngaydat", "ngaytao", "thoigiantao", "ngaymua", "date", "createdat"],
    "channel": ["channel", "kenhban", "kenh", "nguondon", "san", "platform", "store"],
    "status": ["status", "trangthai", "tinhtrangdon", "trangthaidon", "orderstatus"],
    "customer_id": ["customerid", "makhachhang", "makhach", "buyerid", "userid", "sdt", "sodienthoai"],
    "customer_name": ["customername", "tenkhachhang", "tenkhach", "nguoimua", "buyername"],
    "city": ["city", "tinhthanh", "tinh", "thanhpho", "khuvuc", "province"],
    "sku_code": ["skucode", "masku", "mahang", "masanpham", "sku", "itemid"],
    "product_name": ["productname", "tensanpham", "tenhang", "sanpham", "itemname"],
    "category": ["category", "danhmuc", "nhomhang", "loaisanpham"],
    "quantity": ["quantity", "soluong", "sl", "qty", "units"],
    "unit_list_price": ["unitlistprice", "listprice", "dongia", "giaban", "gianiemyet", "unitprice", "price"],
    "unit_cogs": ["unitcogs", "cogs", "giavon", "giavondv", "gianhap", "cost"],
    "seller_discount": ["sellerdiscount", "vouchershop", "giamgiashop", "chietkhau", "discount", "trogiashop"],
    "platform_fee": ["platformfee", "phisan", "phicodinh", "phihoahongsan", "commissionfee"],
    "payment_fee": ["paymentfee", "phithanhtoan", "transactionfee"],
    "affiliate_fee": ["affiliatefee", "hoahongaffiliate", "phiaffiliate", "kolcommission", "affiliate"],
    "shipping_seller": ["shippingseller", "phishipshop", "trogiaship", "sellershipping"],
    "ad_spend": ["adspend", "chiphiads", "quangcao", "ads", "marketingcost"],
    "current_stock": ["currentstock", "tonkho", "tonhientai", "slton", "stock"],
    "lead_time_days": ["leadtimedays", "leadtime", "thoigiannhaphang", "ngaychonhap"],
}


def _norm_header(col_name: Any) -> str:
    txt = str(col_name or "").strip().lower()
    txt = txt.replace("đ", "d")
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", txt)


def _clean_vnd_number(val: Any, default: float = 0.0) -> tuple[float, bool]:
    """Parse messy VN/EN currency strings like '189.000 đ', '189,000', '(25.000)'."""
    if val is None or pd.isna(val):
        return default, False
    if isinstance(val, (int, float, np.number)):
        return float(val), False

    raw = str(val).strip()
    if not raw or raw in ("-", "--", "N/A", "null", "None"):
        return default, False

    was_dirty = False
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
        was_dirty = True
    if any(sym in raw.lower() for sym in ("đ", "vnd", "vnđ", "₫", " ", "k")):
        was_dirty = True

    s = raw.lower().replace("vnđ", "").replace("vnd", "").replace("đ", "").replace("₫", "").strip()
    if s.startswith("-"):
        neg = True
        s = s[1:].strip()

    # Handle '150k' shorthand
    k_mult = 1.0
    if s.endswith("k"):
        k_mult = 1000.0
        s = s[:-1].strip()

    # Distinguish thousand separators from decimal separators: e.g. '189.000' or '1.250.000'
    if re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
        was_dirty = True
    elif re.match(r"^\d{1,3}(,\d{3})+$", s):
        s = s.replace(",", "")
        was_dirty = True
    else:
        s = s.replace(",", "")

    s = re.sub(r"[^0-9.]", "", s)
    if not s:
        return default, was_dirty
    try:
        num = float(s) * k_mult
        return (-num if neg else num), was_dirty
    except ValueError:
        return default, True


def _clean_date_str(val: Any) -> tuple[str, bool]:
    if pd.isna(val):
        return datetime.now().strftime("%Y-%m-%d"), True
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime("%Y-%m-%d"), False
    s = str(val).strip()
    # Fast ISO check
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10], False
    # Vietnamese dd/mm/yyyy or dd-mm-yyyy
    m_vn = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
    if m_vn:
        d_i, m_i, y_i = int(m_vn.group(1)), int(m_vn.group(2)), int(m_vn.group(3))
        if m_i > 12 and d_i <= 12:
            d_i, m_i = m_i, d_i
        try:
            return f"{y_i:04d}-{m_i:02d}-{d_i:02d}", True
        except ValueError:
            pass
    parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d"), True
    return datetime.now().strftime("%Y-%m-%d"), True


def _normalize_status(val: Any) -> str:
    s = _norm_header(val)
    if any(k in s for k in ("return", "hoan", "trahang", "bom", "thatbai", "failed", "refund")):
        return "RETURNED"
    if any(k in s for k in ("cancel", "dahuy", "huy", "void")):
        return "CANCELLED"
    return "COMPLETED"


def import_orders_file(
    file_bytes: bytes,
    filename: str,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """
    Parse an uploaded CSV or XLSX order/SKU dataset, clean Vietnamese dirty fields,
    and materialize it into the ProfitPulse SQLite analytical warehouse.
    """
    lower_name = filename.lower()
    bio = BytesIO(file_bytes)
    if lower_name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(bio)
    elif lower_name.endswith(".csv"):
        try:
            df = pd.read_csv(bio, encoding="utf-8-sig")
        except UnicodeDecodeError:
            bio.seek(0)
            df = pd.read_csv(bio, encoding="latin1")
    else:
        raise ValueError("Chỉ hỗ trợ tệp bảng tính .xlsx hoặc .csv.")

    if df.empty:
        raise ValueError("Tệp tải lên không có dòng dữ liệu nào.")

    # Drop completely empty rows & exact duplicate rows
    raw_row_count = len(df)
    df = df.dropna(how="all")
    dedup_before = len(df)
    df = df.drop_duplicates()
    duplicates_removed = dedup_before - len(df)

    # Auto-map columns
    mapped_cols: dict[str, str] = {}
    norm_to_orig = {_norm_header(c): c for c in df.columns}
    for canonical, aliases in COLUMN_SYNONYMS.items():
        for alias in aliases:
            if alias in norm_to_orig:
                mapped_cols[canonical] = norm_to_orig[alias]
                break

    required_minimum = ["sku_code", "unit_list_price"]
    missing = [r for r in required_minimum if r not in mapped_cols]
    if missing:
        raise ValueError(
            "Không tìm thấy cột tối thiểu bắt buộc (Mã SKU / sku_code và Đơn giá / list_price). "
            "Hãy tải File Mẫu Excel (.xlsx) trên thanh công cụ để xem cấu trúc chuẩn."
        )

    ds_id = "custom_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_title = (dataset_name or filename.rsplit(".", 1)[0]).strip()

    dirty_numbers_fixed = 0
    dirty_dates_fixed = 0

    skus_seen: dict[str, dict[str, Any]] = {}
    customers_seen: dict[str, dict[str, Any]] = {}
    orders_agg: dict[str, dict[str, Any]] = {}
    item_rows: list[tuple[Any, ...]] = []
    mkt_agg: dict[tuple[str, str, str], float] = {}

    for idx, row in df.iterrows():
        ord_id = str(row[mapped_cols["order_id"]]).strip() if "order_id" in mapped_cols and pd.notna(row[mapped_cols["order_id"]]) else f"IMP-ORD-{idx + 1:05d}"
        dt_str, dt_dirty = _clean_date_str(row[mapped_cols["order_date"]]) if "order_date" in mapped_cols else (datetime.now().strftime("%Y-%m-%d"), False)
        if dt_dirty:
            dirty_dates_fixed += 1
        ym_str = dt_str[:7]

        channel = str(row[mapped_cols["channel"]]).strip() if "channel" in mapped_cols and pd.notna(row[mapped_cols["channel"]]) else "Shopee / Kênh Chung"
        status = _normalize_status(row[mapped_cols["status"]]) if "status" in mapped_cols else "COMPLETED"

        cust_id = str(row[mapped_cols["customer_id"]]).strip() if "customer_id" in mapped_cols and pd.notna(row[mapped_cols["customer_id"]]) else f"CUS-IMP-{(idx % 250) + 1:04d}"
        cust_name = str(row[mapped_cols["customer_name"]]).strip() if "customer_name" in mapped_cols and pd.notna(row[mapped_cols["customer_name"]]) else f"Khách hàng {cust_id[-4:]}"
        city = str(row[mapped_cols["city"]]).strip() if "city" in mapped_cols and pd.notna(row[mapped_cols["city"]]) else "TP. Hồ Chí Minh"

        sku_code = str(row[mapped_cols["sku_code"]]).strip().upper()
        prod_name = str(row[mapped_cols["product_name"]]).strip() if "product_name" in mapped_cols and pd.notna(row[mapped_cols["product_name"]]) else f"Sản phẩm {sku_code}"
        category = str(row[mapped_cols["category"]]).strip() if "category" in mapped_cols and pd.notna(row[mapped_cols["category"]]) else "Tổng hợp"

        qty_val, d1 = _clean_vnd_number(row[mapped_cols["quantity"]], 1.0) if "quantity" in mapped_cols else (1.0, False)
        qty = max(1, int(round(qty_val)))
        unit_price, d2 = _clean_vnd_number(row[mapped_cols["unit_list_price"]], 100000.0)
        unit_price = max(1000.0, unit_price)

        if "unit_cogs" in mapped_cols:
            unit_cogs, d3 = _clean_vnd_number(row[mapped_cols["unit_cogs"]], unit_price * 0.45)
        else:
            unit_cogs, d3 = round(unit_price * 0.45), False

        line_gross = unit_price * qty
        seller_disc, d4 = _clean_vnd_number(row[mapped_cols["seller_discount"]], 0.0) if "seller_discount" in mapped_cols else (0.0, False)
        plat_fee_in, d5 = _clean_vnd_number(row[mapped_cols["platform_fee"]], -1.0) if "platform_fee" in mapped_cols else (-1.0, False)
        pay_fee_in, d6 = _clean_vnd_number(row[mapped_cols["payment_fee"]], -1.0) if "payment_fee" in mapped_cols else (-1.0, False)
        aff_fee_in, d7 = _clean_vnd_number(row[mapped_cols["affiliate_fee"]], 0.0) if "affiliate_fee" in mapped_cols else (0.0, False)
        ship_in, d8 = _clean_vnd_number(row[mapped_cols["shipping_seller"]], 0.0) if "shipping_seller" in mapped_cols else (0.0, False)
        ad_in, d9 = _clean_vnd_number(row[mapped_cols["ad_spend"]], 0.0) if "ad_spend" in mapped_cols else (0.0, False)
        stock_in, _ = _clean_vnd_number(row[mapped_cols["current_stock"]], 120.0) if "current_stock" in mapped_cols else (120.0, False)
        lt_in, _ = _clean_vnd_number(row[mapped_cols["lead_time_days"]], 7.0) if "lead_time_days" in mapped_cols else (7.0, False)

        dirty_numbers_fixed += sum(1 for flag in (d1, d2, d3, d4, d5, d6, d7, d8, d9) if flag)

        pack_unit = round(max(3000.0, unit_price * 0.02))
        if status == "COMPLETED":
            net_rev = max(0.0, line_gross - seller_disc)
            cogs_tot = unit_cogs * qty
            pack_tot = pack_unit * qty
            p_fee = plat_fee_in if plat_fee_in >= 0 else round(net_rev * (0.08 if "shopee" in channel.lower() or "tiktok" in channel.lower() else 0.0))
            pay_fee = pay_fee_in if pay_fee_in >= 0 else round(net_rev * 0.025)
            a_fee = max(0.0, aff_fee_in)
            s_ship = max(0.0, ship_in)
            ret_loss = 0.0
        elif status == "RETURNED":
            net_rev = cogs_tot = pack_tot = p_fee = pay_fee = a_fee = s_ship = 0.0
            ret_loss = round(pack_unit * qty + 24000.0 + unit_cogs * qty * 0.10)
        else:
            net_rev = cogs_tot = pack_tot = p_fee = pay_fee = a_fee = s_ship = ret_loss = 0.0

        skus_seen.setdefault(
            sku_code,
            {
                "product_name": prod_name,
                "category": category,
                "list_price": unit_price,
                "unit_cogs": unit_cogs,
                "packaging_cost": pack_unit,
                "current_stock": max(0, int(round(stock_in))),
                "lead_time_days": max(1, int(round(lt_in))),
            },
        )

        c_rec = customers_seen.get(cust_id)
        if not c_rec or dt_str < c_rec["first_order_date"]:
            customers_seen[cust_id] = {
                "customer_name": cust_name,
                "phone_masked": f"09***{cust_id[-3:]}",
                "city": city,
                "acquisition_channel": channel,
                "acquisition_cost": 45000.0,
                "first_order_date": dt_str,
            }

        o_rec = orders_agg.setdefault(
            ord_id,
            {
                "order_date": dt_str,
                "order_month": ym_str,
                "channel": channel,
                "customer_id": cust_id,
                "status": status,
                "gross_amount": 0.0,
                "seller_voucher": 0.0,
                "shipping_fee_seller": 0.0,
                "return_logistics_fee": 0.0,
                "platform_fee": 0.0,
                "payment_fee": 0.0,
                "affiliate_fee": 0.0,
            },
        )
        o_rec["gross_amount"] += line_gross
        o_rec["seller_voucher"] += seller_disc
        o_rec["shipping_fee_seller"] += s_ship
        o_rec["return_logistics_fee"] += ret_loss
        o_rec["platform_fee"] += p_fee
        o_rec["payment_fee"] += pay_fee
        o_rec["affiliate_fee"] += a_fee

        item_rows.append(
            (
                ds_id,
                ord_id,
                sku_code,
                qty,
                unit_price,
                line_gross,
                seller_disc,
                net_rev,
                cogs_tot,
                pack_tot,
                p_fee,
                pay_fee,
                a_fee,
                s_ship,
                ret_loss,
            )
        )

        if ad_in > 0:
            key = (dt_str, channel, sku_code)
            mkt_agg[key] = mkt_agg.get(key, 0.0) + ad_in

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    delete_dataset(ds_id)
    with get_connection(readonly=False) as conn:
        conn.execute(
            """
            INSERT INTO datasets (dataset_id, name, industry, description, currency, created_at, is_builtin)
            VALUES (?, ?, 'Custom Uploaded Data', ?, 'VND', ?, 0)
            """,
            (
                ds_id,
                f"📂 {clean_title}",
                f"Dữ liệu thực tế tải lên từ tệp {filename} ({len(orders_agg)} đơn hàng, {len(skus_seen)} SKU).",
                now_iso,
            ),
        )
        conn.executemany(
            """
            INSERT INTO skus (
                dataset_id, sku_code, product_name, category, list_price, unit_cogs,
                packaging_cost, current_stock, lead_time_days, min_order_qty, price_elasticity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 30, -1.35)
            """,
            [
                (
                    ds_id,
                    code,
                    s["product_name"],
                    s["category"],
                    s["list_price"],
                    s["unit_cogs"],
                    s["packaging_cost"],
                    s["current_stock"],
                    s["lead_time_days"],
                )
                for code, s in skus_seen.items()
            ],
        )
        conn.executemany(
            """
            INSERT INTO customers (
                dataset_id, customer_id, customer_name, phone_masked, city,
                acquisition_channel, acquisition_cost, first_order_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ds_id,
                    cid,
                    c["customer_name"],
                    c["phone_masked"],
                    c["city"],
                    c["acquisition_channel"],
                    c["acquisition_cost"],
                    c["first_order_date"],
                )
                for cid, c in customers_seen.items()
            ],
        )
        conn.executemany(
            """
            INSERT INTO orders (
                dataset_id, order_id, order_date, order_month, channel, customer_id, status,
                gross_amount, seller_voucher, platform_subsidy, shipping_fee_seller,
                return_logistics_fee, platform_fee, payment_fee, affiliate_fee
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ds_id,
                    oid,
                    o["order_date"],
                    o["order_month"],
                    o["channel"],
                    o["customer_id"],
                    o["status"],
                    o["gross_amount"],
                    o["seller_voucher"],
                    o["shipping_fee_seller"],
                    o["return_logistics_fee"],
                    o["platform_fee"],
                    o["payment_fee"],
                    o["affiliate_fee"],
                )
                for oid, o in orders_agg.items()
            ],
        )
        conn.executemany(
            """
            INSERT INTO order_items (
                dataset_id, order_id, sku_code, quantity, unit_list_price, item_gross,
                item_seller_discount, item_net_revenue, item_cogs, item_packaging_cost,
                item_platform_fee, item_payment_fee, item_affiliate_fee, item_shipping_seller, item_return_loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            item_rows,
        )
        if mkt_agg:
            conn.executemany(
                """
                INSERT INTO marketing_daily (
                    dataset_id, spend_date, spend_month, channel, sku_code, ad_spend, impressions, clicks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (ds_id, dt_s, dt_s[:7], ch_s, sk_s, sp_v, int(sp_v / 90), max(1, int(sp_v / 3200)))
                    for (dt_s, ch_s, sk_s), sp_v in mkt_agg.items()
                ],
            )
        conn.commit()

    return {
        "dataset_id": ds_id,
        "name": f"📂 {clean_title}",
        "audit": {
            "raw_rows": raw_row_count,
            "imported_lines": len(item_rows),
            "unique_orders": len(orders_agg),
            "unique_skus": len(skus_seen),
            "unique_customers": len(customers_seen),
            "duplicates_removed": duplicates_removed,
            "dirty_numbers_cleaned": dirty_numbers_fixed,
            "dirty_dates_standardized": dirty_dates_fixed,
            "mapped_columns": mapped_cols,
        },
    }


def _style_worksheet(ws) -> None:
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(44, max(13, max_len + 4))


def build_import_template_xlsx() -> bytes:
    """Create a downloadable .xlsx template with realistic Vietnamese sample rows (including messy formats)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Don_Hang_Mau"
    headers = [
        "Mã đơn hàng",
        "Ngày đặt",
        "Kênh bán",
        "Trạng thái",
        "Mã khách hàng",
        "Tên khách hàng",
        "Tỉnh thành",
        "Mã SKU",
        "Tên sản phẩm",
        "Danh mục",
        "Số lượng",
        "Đơn giá",
        "Giá vốn",
        "Voucher Shop",
        "Phí sàn",
        "Hoa hồng Affiliate",
        "Chi phí Ads",
        "Tồn kho hiện tại",
        "Lead time",
    ]
    ws.append(headers)
    sample_rows = [
        ["SHP-2610-001", "15/09/2026", "Shopee Mall", "Hoàn thành", "KH001", "Nguyễn Minh Anh", "TP. Hồ Chí Minh", "SKU-AO-01", "Áo Sơ Mi Oxford Trắng", "Áo Sơ Mi", 2, "389.000 đ", 142000, 30000, 62000, 0, 25000, 45, 10],
        ["TTK-2610-002", "16/09/2026", "TikTok Shop", "Hoàn thành", "KH002", "Trần Thảo Linh", "Hà Nội", "SKU-THUN-02", "Áo Thun Basic Mồi", "Áo Thun", 1, 159000, 82000, 35000, 13000, 18000, 32000, 320, 7],
        ["TTK-2610-003", "2026-10-10", "TikTok Shop", "Hoàn trả", "KH003", "Lê Hoàng Nam", "Đà Nẵng", "SKU-BLZ-03", "Áo Blazer 2 Lớp", "Áo Khoác", 1, "690,000", 345000, 50000, 0, 0, 40000, 85, 14],
        ["WEB-2610-004", "18/10/2026", "Website D2C", "Hoàn thành", "KH001", "Nguyễn Minh Anh", "TP. Hồ Chí Minh", "SKU-QUAN-04", "Quần Âu Slimfit", "Quần Dài", 1, 449000, 168000, 20000, 9500, 0, 15000, 110, 10],
        ["POS-2610-005", "22/10/2026", "Cửa hàng POS", "Hoàn thành", "KH004", "Phạm Quốc Tuấn", "TP. Hồ Chí Minh", "SKU-AO-01", "Áo Sơ Mi Oxford Trắng", "Áo Sơ Mi", 1, 389000, 142000, 0, 3000, 0, 0, 45, 10],
    ]
    for sr in sample_rows:
        ws.append(sr)
    _style_worksheet(ws)

    ws_guide = wb.create_sheet("Huong_Dan_Cot")
    ws_guide.append(["Tên cột tiếng Việt / Anh", "Bắt buộc?", "Giải thích & Khả năng tự làm sạch dữ liệu bẩn"])
    guide_rows = [
        ["Mã SKU / sku_code", "BẮT BUỘC", "Mã định danh sản phẩm (tự động chuẩn hóa IN HOA)."],
        ["Đơn giá / list_price", "BẮT BUỘC", "Chấp nhận số thô hoặc chuỗi bẩn kiểu '389.000 đ', '389,000', '389k'."],
        ["Mã đơn hàng / order_id", "Khuyến nghị", "Nếu bỏ trống hệ thống tự đánh mã theo dòng."],
        ["Ngày đặt / order_date", "Khuyến nghị", "Tự động nhận diện chuẩn VN dd/mm/yyyy và chuẩn ISO yyyy-mm-dd."],
        ["Trạng thái / status", "Khuyến nghị", "Nhận diện 'Hoàn thành', 'Trả hàng / Hoàn tiền / Bom', 'Đã hủy'."],
        ["Giá vốn / unit_cogs", "Khuyến nghị", "Giá nhập 1 đơn vị. Nếu thiếu sẽ tạm ước tính 45% đơn giá."],
        ["Voucher Shop, Phí sàn, Affiliate, Ads", "Tùy chọn", "Giúp bóc tách chính xác Lãi Ròng Thực & Bẫy Doanh Thu Ảo."],
        ["Tồn kho hiện tại & Lead time", "Tùy chọn", "Dùng để tính Ma trận ABC-XYZ, Điểm đặt hàng lại (ROP) & Cảnh báo đứt hàng."],
    ]
    for gr in guide_rows:
        ws_guide.append(gr)
    _style_worksheet(ws_guide)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_executive_report_xlsx(dataset_id: str) -> bytes:
    """Export a full 5-sheet Executive BI Excel Report for managers / stakeholders."""
    pnl = get_pnl_overview(dataset_id)
    rfm = get_rfm_cohort_and_optimizer(dataset_id, budget_vnd=15_000_000)
    inv = get_inventory_abc_xyz(dataset_id)

    wb = Workbook()
    # Sheet 1: Waterfall & KPIs
    ws1 = wb.active
    ws1.title = "1_Tong_Quan_PnL"
    ws1.append(["Chỉ tiêu P&L Đa Kênh", "Giá trị (VNĐ / %)"])
    k = pnl["kpis"]
    kpi_pairs = [
        ("Tổng GMV Đơn Thành Công", k["completed_gross"]),
        ("Trợ giá / Voucher Shop", -k["seller_discount"]),
        ("Doanh Thu Thuần (Net Revenue)", k["net_revenue"]),
        ("Giá Vốn + Bao Bì Đóng Gói", -k["cogs_pack"]),
        ("Phí Sàn & Cổng Thanh Toán", -k["platform_and_payment_fees"]),
        ("Hoa Hồng Affiliate / KOL", -k["affiliate_fee"]),
        ("Trợ Giá Vận Chuyển Shop Chịu", -k["shipping_seller"]),
        ("Thiệt Hại Đơn Hoàn / Bom Hàng", -k["return_loss"]),
        ("Chi Phí Quảng Cáo Ads", -k["ad_spend"]),
        ("LÃI RÒNG THỰC TẾ BỎ TÚI", k["true_net_profit"]),
        ("Biên Lãi Ròng Thực (%)", f"{k['net_margin_pct']}%"),
        ("Tỷ Lệ Đơn Hoàn (%)", f"{k['return_rate_pct']}%"),
        ("ROAS Doanh Thu / POAS Lợi Nhuận", f"{k['roas']}x / {k['poas']}x"),
    ]
    for row in kpi_pairs:
        ws1.append(list(row))
    _style_worksheet(ws1)

    # Sheet 2: Channel P&L
    ws2 = wb.create_sheet("2_Hieu_Qua_Kenh")
    ws2.append(["Kênh Bán", "Đơn Thành Công", "Đơn Hoàn", "Tỷ Lệ Hoàn %", "Doanh Thu Thuần", "Tổng Phí Sàn & Ship", "Thiệt Hại Hoàn", "Chi Phí Ads", "Lãi Ròng Thực", "Biên Lãi Ròng %"])
    for c in pnl["channels_pnl"]:
        ws2.append([c["channel"], c["completed_orders"], c["returned_orders"], c["return_rate_pct"], c["net_rev"], c["channel_fees"], c["return_loss"], c["ad_spend"], c["net_profit"], c["net_margin_pct"]])
    _style_worksheet(ws2)

    # Sheet 3: SKU P&L
    ws3 = wb.create_sheet("3_Lai_Lo_Theo_SKU")
    ws3.append(["Mã SKU", "Tên Sản Phẩm", "Danh Mục", "SL Bán", "Hoàn %", "Doanh Thu Thuần", "Giá Vốn & Gói", "Phí Sàn & Aff", "Lỗ Đơn Hoàn", "Chi Phí Ads", "Lãi Ròng Thực", "Lãi / 1 SP", "Biên Ròng %", "Phân Loại", "Khuyến Nghị Hành Động"])
    for s in pnl["sku_pnl"]:
        ws3.append([s["sku_code"], s["product_name"], s["category"], s["units_sold"], s["return_rate_pct"], s["net_revenue"], s["cogs_pack"], s["fees_total"], s["return_loss"], s["ad_spend"], s["net_profit"], s["profit_per_unit"], s["net_margin_pct"], s["badge_label"], s["advice"]])
    _style_worksheet(ws3)

    # Sheet 4: Retention Target List
    ws4 = wb.create_sheet("4_DS_Khach_Can_Cuu_RFM")
    ws4.append(["Mã KH", "Tên Khách Hàng", "SĐT", "Tỉnh Thành", "Phân Khúc RFM", "Điểm RFM", "Số Ngày Chưa Mua", "Số Lần Mua", "LTV Lợi Nhuận Cũ", "Kịch Bản Chăm Sóc", "Chi Phí Dự Kiến", "Lãi Tăng Thêm Kỳ Vọng", "ROI (Lần)"])
    for t in rfm["optimizer"]["top_targets"]:
        ws4.append([t["customer_id"], t["customer_name"], t["phone_masked"], t["city"], t["segment_name"], t["rfm_code"], t["recency_days"], t["frequency"], t["historical_profit"], t["campaign_action"], t["budget_cost"], t["expected_inc_profit"], t["roi_multiple"]])
    _style_worksheet(ws4)

    # Sheet 5: Inventory ABC-XYZ
    ws5 = wb.create_sheet("5_Ton_Kho_ABC_XYZ")
    ws5.append(["Mã SKU", "Tên Sản Phẩm", "Hạng ABC-XYZ", "Tồn Hiện Tại", "Bán TB/Ngày", "Lead Time (Ngày)", "Tồn An Toàn", "Điểm Đặt Hàng Lại (ROP)", "Số Ngày Đủ Bán (DOI)", "Vốn Tồn Kho (VNĐ)", "Đề Xuất Nhập Thêm", "Ngân Sách Nhập (VNĐ)", "Trạng Thái", "Hành Động"])
    for it in inv["items"]:
        ws5.append([it["sku_code"], it["product_name"], it["abc_xyz"], it["current_stock"], it["avg_daily_demand"], it["lead_time_days"], it["safety_stock"], it["reorder_point"], it["days_of_inventory"], it["stock_value_vnd"], it["suggested_order_qty"], it["reorder_budget_vnd"], it["status_label"], it["action_text"]])
    _style_worksheet(ws5)

    # Sheet 6: 30-Day Forecast & Market Basket Combo Bundles
    from .predictive import get_predictive_and_stats_suite
    pred = get_predictive_and_stats_suite(dataset_id)
    ws6 = wb.create_sheet("6_Du_Bao_30N_Va_Combo")
    ws6.append(["Cặp SKU Gợi Ý Ghép Combo", "Chiến Lược", "Đơn Mua Chung", "Confidence %", "Hệ Số Lift", "Giá Lẻ Cộng Gộp", "Giá Bán Combo (-8%)", "Lãi Cũ Khi Bán Rời", "Lãi Ròng Combo 1 Kiện", "Lãi Tăng Thêm / Combo"])
    for b in pred["market_basket_bundles"]:
        ws6.append([
            f"{b['trigger_sku']} + {b['partner_sku']} ({b['trigger_name']} + {b['partner_name']})",
            b["strategy_tag"],
            b["co_orders"],
            b["confidence_pct"],
            b["lift"],
            b["combined_list_price"],
            b["suggested_bundle_price"],
            b["standalone_profit"],
            b["bundle_net_profit"],
            b["profit_uplift_vnd"],
        ])
    _style_worksheet(ws6)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
