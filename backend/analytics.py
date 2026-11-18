"""
Core Analytical Engine for ProfitPulse BI:
1. Unit Economics & Multi-Channel True Net Profit Waterfall
2. Automated Month-over-Month Variance Decomposition Bridge
3. SKU Cash-Cow vs Profit-Bleeder Diagnostics
4. SQL Window-Function RFM Segmentation, Monthly Cohort Retention & Budget Knapsack Optimizer
5. ABC-XYZ Inventory Matrix, Safety Stock, Reorder Point & Dead-Stock Capital Engine
6. Elastic What-If Pricing, Fee & Promo Break-Even Simulator
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import math
import numpy as np
import pandas as pd

from .database import get_connection


def list_datasets() -> list[dict[str, Any]]:
    with get_connection(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT
                d.dataset_id, d.name, d.industry, d.description, d.currency, d.created_at, d.is_builtin,
                (SELECT COUNT(*) FROM orders o WHERE o.dataset_id = d.dataset_id) AS total_orders,
                (SELECT COUNT(*) FROM skus s WHERE s.dataset_id = d.dataset_id) AS total_skus,
                (SELECT COUNT(*) FROM customers c WHERE c.dataset_id = d.dataset_id) AS total_customers,
                (SELECT MIN(order_date) FROM orders o WHERE o.dataset_id = d.dataset_id) AS min_date,
                (SELECT MAX(order_date) FROM orders o WHERE o.dataset_id = d.dataset_id) AS max_date
            FROM datasets d
            ORDER BY
                d.is_builtin ASC,
                CASE d.dataset_id
                    WHEN 'vn_fashion_omni' THEN 1
                    WHEN 'vn_skincare_d2c' THEN 2
                    WHEN 'vn_coffee_chain' THEN 3
                    ELSE 4
                END ASC,
                d.created_at DESC
            """
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            chans = conn.execute(
                "SELECT DISTINCT channel FROM orders WHERE dataset_id = ? ORDER BY channel",
                (item["dataset_id"],),
            ).fetchall()
            skus = conn.execute(
                "SELECT sku_code, product_name, category, list_price FROM skus WHERE dataset_id = ? ORDER BY sku_code",
                (item["dataset_id"],),
            ).fetchall()
            item["channels"] = [c["channel"] for c in chans]
            item["skus"] = [dict(s) for s in skus]
            result.append(item)
    return result


def _build_filter_clause(
    dataset_id: str,
    start_date: str | None,
    end_date: str | None,
    channel: str | None,
    table_alias: str = "o",
    date_col: str = "order_date",
) -> tuple[str, list[Any]]:
    clauses = [f"{table_alias}.dataset_id = ?"]
    params: list[Any] = [dataset_id]
    if start_date:
        clauses.append(f"{table_alias}.{date_col} >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{table_alias}.{date_col} <= ?")
        params.append(end_date)
    if channel and channel != "ALL":
        clauses.append(f"{table_alias}.channel = ?")
        params.append(channel)
    return " AND ".join(clauses), params


def get_pnl_overview(
    dataset_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    where_ord, params_ord = _build_filter_clause(dataset_id, start_date, end_date, channel, "o", "order_date")
    where_mkt, params_mkt = _build_filter_clause(dataset_id, start_date, end_date, channel, "m", "spend_date")

    with get_connection(readonly=True) as conn:
        # 1. Order counts & status funnel
        ord_stats = dict(
            conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_orders,
                     COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS completed_orders,
                    COALESCE(SUM(CASE WHEN o.status = 'RETURNED' THEN 1 ELSE 0 END), 0) AS returned_orders,
                    COALESCE(SUM(CASE WHEN o.status = 'CANCELLED' THEN 1 ELSE 0 END), 0) AS cancelled_orders,
                    COALESCE(SUM(o.gross_amount), 0) AS all_gross_gmv
                FROM orders o
                WHERE {where_ord}
                """,
                params_ord,
            ).fetchone()
        )

        # 2. Item-level realized P&L components
        pnl_row = dict(
            conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_gross ELSE 0 END), 0) AS completed_gross,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_seller_discount ELSE 0 END), 0) AS seller_discount,
                    COALESCE(SUM(oi.item_net_revenue), 0) AS net_revenue,
                    COALESCE(SUM(oi.item_cogs), 0) AS cogs,
                    COALESCE(SUM(oi.item_packaging_cost), 0) AS packaging_cost,
                    COALESCE(SUM(oi.item_platform_fee), 0) AS platform_fee,
                    COALESCE(SUM(oi.item_payment_fee), 0) AS payment_fee,
                    COALESCE(SUM(oi.item_affiliate_fee), 0) AS affiliate_fee,
                    COALESCE(SUM(oi.item_shipping_seller), 0) AS shipping_seller,
                    COALESCE(SUM(oi.item_return_loss), 0) AS return_loss,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END), 0) AS units_sold
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE {where_ord}
                """,
                params_ord,
            ).fetchone()
        )

        mkt_row = dict(
            conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(m.ad_spend), 0) AS ad_spend,
                    COALESCE(SUM(m.clicks), 0) AS clicks,
                    COALESCE(SUM(m.impressions), 0) AS impressions
                FROM marketing_daily m
                WHERE {where_mkt}
                """,
                params_mkt,
            ).fetchone()
        )

        ad_spend = float(mkt_row["ad_spend"])
        completed_gross = float(pnl_row["completed_gross"])
        seller_discount = float(pnl_row["seller_discount"])
        net_revenue = float(pnl_row["net_revenue"])
        cogs_pack = float(pnl_row["cogs"] + pnl_row["packaging_cost"])
        plat_pay_fee = float(pnl_row["platform_fee"] + pnl_row["payment_fee"])
        affiliate_fee = float(pnl_row["affiliate_fee"])
        shipping_seller = float(pnl_row["shipping_seller"])
        return_loss = float(pnl_row["return_loss"])

        gross_profit = net_revenue - cogs_pack
        contribution_before_ads = gross_profit - plat_pay_fee - affiliate_fee - shipping_seller - return_loss
        true_net_profit = contribution_before_ads - ad_spend

        total_orders = max(1, int(ord_stats["total_orders"]))
        non_cancelled = max(1, int(ord_stats["completed_orders"]) + int(ord_stats["returned_orders"]))
        comp_orders = int(ord_stats["completed_orders"])

        net_margin_pct = (true_net_profit / net_revenue * 100.0) if net_revenue > 0 else 0.0
        gross_margin_pct = (gross_profit / net_revenue * 100.0) if net_revenue > 0 else 0.0
        return_rate_pct = float(ord_stats["returned_orders"]) / non_cancelled * 100.0
        cancel_rate_pct = float(ord_stats["cancelled_orders"]) / total_orders * 100.0
        aov = (net_revenue / comp_orders) if comp_orders > 0 else 0.0
        roas = (net_revenue / ad_spend) if ad_spend > 0 else 0.0
        poas = (contribution_before_ads / ad_spend) if ad_spend > 0 else 0.0

        # Waterfall chart steps (exact additive bridge)
        waterfall = [
            {"label": "GMV Đơn Thành Công", "value": round(completed_gross), "type": "total"},
            {"label": "Voucher / Chiết Khấu Shop", "value": -round(seller_discount), "type": "deduct"},
            {"label": "Doanh Thu Thuần", "value": round(net_revenue), "type": "subtotal"},
            {"label": "Giá Vốn + Đóng Gói", "value": -round(cogs_pack), "type": "deduct"},
            {"label": "Phí Sàn & Thanh Toán", "value": -round(plat_pay_fee), "type": "deduct"},
            {"label": "Hoa Hồng Affiliate", "value": -round(affiliate_fee), "type": "deduct"},
            {"label": "Trợ Giá Ship & Đơn Hoàn", "value": -round(shipping_seller + return_loss), "type": "deduct"},
            {"label": "Chi Phí Quảng Cáo Ads", "value": -round(ad_spend), "type": "deduct"},
            {"label": "Lãi Ròng Thực Bỏ Túi", "value": round(true_net_profit), "type": "final"},
        ]

        # 3. Channel P&L Comparison (always compare all channels within date range)
        where_chan, params_chan = _build_filter_clause(dataset_id, start_date, end_date, None, "o", "order_date")
        where_mchan, params_mchan = _build_filter_clause(dataset_id, start_date, end_date, None, "m", "spend_date")
        chan_rows = conn.execute(
            f"""
            WITH chan_orders AS (
                SELECT
                    o.channel,
                    COUNT(DISTINCT o.order_id) AS total_orders,
                    COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) AS completed_orders,
                    COUNT(DISTINCT CASE WHEN o.status = 'RETURNED' THEN o.order_id END) AS returned_orders
                FROM orders o
                WHERE {where_chan}
                GROUP BY o.channel
            ),
            chan_items AS (
                SELECT
                    o.channel,
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_gross ELSE 0 END) AS gross_rev,
                    SUM(oi.item_net_revenue) AS net_rev,
                    SUM(oi.item_cogs + oi.item_packaging_cost) AS cogs_pack,
                    SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee + oi.item_shipping_seller) AS channel_fees,
                    SUM(oi.item_return_loss) AS return_loss
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE {where_chan}
                GROUP BY o.channel
            ),
            chan_ads AS (
                SELECT m.channel, SUM(m.ad_spend) AS ad_spend
                FROM marketing_daily m
                WHERE {where_mchan}
                GROUP BY m.channel
            )
            SELECT
                co.channel,
                co.total_orders,
                co.completed_orders,
                co.returned_orders,
                COALESCE(ci.gross_rev, 0) AS gross_rev,
                COALESCE(ci.net_rev, 0) AS net_rev,
                COALESCE(ci.cogs_pack, 0) AS cogs_pack,
                COALESCE(ci.channel_fees, 0) AS channel_fees,
                COALESCE(ci.return_loss, 0) AS return_loss,
                COALESCE(ca.ad_spend, 0) AS ad_spend
            FROM chan_orders co
            LEFT JOIN chan_items ci ON ci.channel = co.channel
            LEFT JOIN chan_ads ca ON ca.channel = co.channel
            ORDER BY ci.net_rev DESC
            """,
            params_chan + params_chan + params_mchan,
        ).fetchall()

        channels_pnl = []
        for cr in chan_rows:
            d = dict(cr)
            n_rev = float(d["net_rev"])
            n_prof = n_rev - float(d["cogs_pack"]) - float(d["channel_fees"]) - float(d["return_loss"]) - float(d["ad_spend"])
            shipped = max(1, int(d["completed_orders"]) + int(d["returned_orders"]))
            fee_burden_pct = ((float(d["channel_fees"]) + float(d["ad_spend"])) / n_rev * 100.0) if n_rev > 0 else 0.0
            channels_pnl.append(
                {
                    **d,
                    "net_profit": round(n_prof),
                    "net_margin_pct": round((n_prof / n_rev * 100.0) if n_rev > 0 else 0.0, 2),
                    "return_rate_pct": round(int(d["returned_orders"]) / shipped * 100.0, 2),
                    "fee_and_ads_pct": round(fee_burden_pct, 2),
                }
            )

        # 4. Monthly Trend Series
        monthly_rows = conn.execute(
            f"""
            WITH m_items AS (
                SELECT
                    o.order_month AS ym,
                    COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) AS completed_orders,
                    SUM(oi.item_net_revenue) AS net_rev,
                    SUM(oi.item_cogs + oi.item_packaging_cost) AS cogs_pack,
                    SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee + oi.item_shipping_seller) AS fees,
                    SUM(oi.item_return_loss) AS return_loss
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE {where_ord}
                GROUP BY o.order_month
            ),
            m_ads AS (
                SELECT m.spend_month AS ym, SUM(m.ad_spend) AS ad_spend
                FROM marketing_daily m
                WHERE {where_mkt}
                GROUP BY m.spend_month
            )
            SELECT
                mi.ym,
                mi.completed_orders,
                mi.net_rev,
                mi.cogs_pack,
                mi.fees,
                mi.return_loss,
                COALESCE(ma.ad_spend, 0) AS ad_spend
            FROM m_items mi
            LEFT JOIN m_ads ma ON ma.ym = mi.ym
            ORDER BY mi.ym ASC
            """,
            params_ord + params_mkt,
        ).fetchall()

        monthly_trend = []
        for mr in monthly_rows:
            md = dict(mr)
            np_val = float(md["net_rev"]) - float(md["cogs_pack"]) - float(md["fees"]) - float(md["return_loss"]) - float(md["ad_spend"])
            monthly_trend.append(
                {
                    "month": md["ym"],
                    "completed_orders": int(md["completed_orders"]),
                    "net_revenue": round(float(md["net_rev"])),
                    "fees_and_returns": round(float(md["fees"]) + float(md["return_loss"])),
                    "ad_spend": round(float(md["ad_spend"])),
                    "net_profit": round(np_val),
                    "net_margin_pct": round((np_val / float(md["net_rev"]) * 100.0) if float(md["net_rev"]) > 0 else 0.0, 2),
                }
            )

        # 5. SKU-level Profitability Matrix (Cash Cows vs Profit Bleeders)
        sku_rows = conn.execute(
            f"""
            WITH sku_sales AS (
                SELECT
                    oi.sku_code,
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END) AS units_sold,
                    COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) AS completed_orders,
                    COUNT(DISTINCT CASE WHEN o.status = 'RETURNED' THEN o.order_id END) AS returned_orders,
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_gross ELSE 0 END) AS gross_rev,
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_seller_discount ELSE 0 END) AS seller_disc,
                    SUM(oi.item_net_revenue) AS net_rev,
                    SUM(oi.item_cogs + oi.item_packaging_cost) AS cogs_pack,
                    SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_shipping_seller) AS plat_fees,
                    SUM(oi.item_affiliate_fee) AS aff_fees,
                    SUM(oi.item_return_loss) AS return_loss
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE {where_ord}
                GROUP BY oi.sku_code
            ),
            sku_ads AS (
                SELECT m.sku_code, SUM(m.ad_spend) AS ad_spend
                FROM marketing_daily m
                WHERE {where_mkt}
                GROUP BY m.sku_code
            )
            SELECT
                s.sku_code,
                s.product_name,
                s.category,
                s.list_price,
                s.unit_cogs,
                COALESCE(ss.units_sold, 0) AS units_sold,
                COALESCE(ss.completed_orders, 0) AS completed_orders,
                COALESCE(ss.returned_orders, 0) AS returned_orders,
                COALESCE(ss.gross_rev, 0) AS gross_rev,
                COALESCE(ss.seller_disc, 0) AS seller_disc,
                COALESCE(ss.net_rev, 0) AS net_rev,
                COALESCE(ss.cogs_pack, 0) AS cogs_pack,
                COALESCE(ss.plat_fees, 0) AS plat_fees,
                COALESCE(ss.aff_fees, 0) AS aff_fees,
                COALESCE(ss.return_loss, 0) AS return_loss,
                COALESCE(sa.ad_spend, 0) AS ad_spend
            FROM skus s
            LEFT JOIN sku_sales ss ON ss.sku_code = s.sku_code
            LEFT JOIN sku_ads sa ON sa.sku_code = s.sku_code
            WHERE s.dataset_id = ?
            ORDER BY COALESCE(ss.net_rev, 0) DESC
            """,
            params_ord + params_mkt + [dataset_id],
        ).fetchall()

        sku_pnl = []
        median_rev = float(np.median([float(r["net_rev"]) for r in sku_rows])) if sku_rows else 0.0
        for sr in sku_rows:
            sd = dict(sr)
            u_sold = int(sd["units_sold"])
            n_rev = float(sd["net_rev"])
            n_prof = (
                n_rev
                - float(sd["cogs_pack"])
                - float(sd["plat_fees"])
                - float(sd["aff_fees"])
                - float(sd["return_loss"])
                - float(sd["ad_spend"])
            )
            shipped = max(1, int(sd["completed_orders"]) + int(sd["returned_orders"]))
            ret_pct = int(sd["returned_orders"]) / shipped * 100.0
            n_margin = (n_prof / n_rev * 100.0) if n_rev > 0 else 0.0
            disc_pct = (float(sd["seller_disc"]) / float(sd["gross_rev"]) * 100.0) if float(sd["gross_rev"]) > 0 else 0.0
            ad_ratio = (float(sd["ad_spend"]) / n_rev * 100.0) if n_rev > 0 else 0.0

            if n_prof < 0:
                badge = "BLEEDER"
                badge_label = "🩸 Lỗ Ngầm (Bleeder)"
                if ad_ratio > 18 or disc_pct > 15:
                    advice = f"Cắt giảm trợ giá ({disc_pct:.1f}%) & giới hạn Ads ({ad_ratio:.1f}% DT); chỉ bán kèm Combo tăng AOV."
                elif ret_pct > 14:
                    advice = f"Tỷ lệ hoàn cao ({ret_pct:.1f}%) ăn mòn lãi — cập nhật bảng size/mô tả & siết QC đóng gói."
                else:
                    advice = "Tăng giá niêm yết 8–12% hoặc đàm phán lại giá vốn/hoa hồng Affiliate."
            elif n_margin >= 18 and n_rev >= median_rev:
                badge = "STAR"
                badge_label = "🌟 Chủ Lực Lãi Cao"
                advice = "Ưu tiên ngân sách Ads & giữ tồn kho an toàn tuyệt đối tránh đứt hàng."
            elif n_rev >= median_rev:
                badge = "CASH_COW"
                badge_label = "🐄 Bò Sữa Giữ Nhịp"
                advice = "Tối ưu chuyển đổi sang kênh riêng (Web/Zalo/POS) để tiết kiệm 8–12% phí sàn."
            else:
                badge = "NICHE"
                badge_label = "🧩 Ngách / Chậm"
                advice = "Gom bán chéo (Cross-sell) cùng sản phẩm chủ lực, hạn chế nhập thêm lô lớn."

            sku_pnl.append(
                {
                    "sku_code": sd["sku_code"],
                    "product_name": sd["product_name"],
                    "category": sd["category"],
                    "list_price": round(float(sd["list_price"])),
                    "units_sold": u_sold,
                    "return_rate_pct": round(ret_pct, 1),
                    "discount_pct": round(disc_pct, 1),
                    "net_revenue": round(n_rev),
                    "cogs_pack": round(float(sd["cogs_pack"])),
                    "fees_total": round(float(sd["plat_fees"]) + float(sd["aff_fees"])),
                    "return_loss": round(float(sd["return_loss"])),
                    "ad_spend": round(float(sd["ad_spend"])),
                    "net_profit": round(n_prof),
                    "profit_per_unit": round(n_prof / u_sold) if u_sold > 0 else 0,
                    "net_margin_pct": round(n_margin, 2),
                    "badge": badge,
                    "badge_label": badge_label,
                    "advice": advice,
                }
            )

        # 6. Month-over-Month Variance Decomposition Bridge (Last 2 available months)
        variance_bridge = _compute_mom_variance_bridge(conn, dataset_id, channel)

    return {
        "kpis": {
            "all_gross_gmv": round(float(ord_stats["all_gross_gmv"])),
            "completed_gross": round(completed_gross),
            "seller_discount": round(seller_discount),
            "net_revenue": round(net_revenue),
            "cogs_pack": round(cogs_pack),
            "platform_and_payment_fees": round(plat_pay_fee),
            "affiliate_fee": round(affiliate_fee),
            "shipping_seller": round(shipping_seller),
            "return_loss": round(return_loss),
            "ad_spend": round(ad_spend),
            "true_net_profit": round(true_net_profit),
            "gross_margin_pct": round(gross_margin_pct, 2),
            "net_margin_pct": round(net_margin_pct, 2),
            "total_orders": int(ord_stats["total_orders"]),
            "completed_orders": comp_orders,
            "returned_orders": int(ord_stats["returned_orders"]),
            "return_rate_pct": round(return_rate_pct, 2),
            "cancel_rate_pct": round(cancel_rate_pct, 2),
            "units_sold": int(pnl_row["units_sold"]),
            "aov": round(aov),
            "roas": round(roas, 2),
            "poas": round(poas, 2),
        },
        "waterfall": waterfall,
        "channels_pnl": channels_pnl,
        "monthly_trend": monthly_trend,
        "sku_pnl": sku_pnl,
        "variance_bridge": variance_bridge,
    }


def _compute_mom_variance_bridge(conn, dataset_id: str, channel: str | None) -> dict[str, Any]:
    """Decompose Net Profit change between the latest two months into actionable drivers."""
    chan_clause = " AND o.channel = ?" if (channel and channel != "ALL") else ""
    m_chan_clause = " AND m.channel = ?" if (channel and channel != "ALL") else ""
    chan_param = [channel] if (channel and channel != "ALL") else []

    months = [
        r["order_month"]
        for r in conn.execute(
            f"SELECT DISTINCT o.order_month FROM orders o WHERE o.dataset_id = ? {chan_clause} ORDER BY o.order_month DESC LIMIT 2",
            [dataset_id] + chan_param,
        ).fetchall()
    ]
    if len(months) < 2:
        return {"available": False, "steps": [], "insights": []}

    curr_m, prev_m = months[0], months[1]

    def _month_snapshot(ym: str) -> dict[str, float]:
        r = dict(
            conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END), 0) AS qty,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_gross ELSE 0 END), 0) AS gross,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_seller_discount ELSE 0 END), 0) AS disc,
                    COALESCE(SUM(oi.item_net_revenue), 0) AS net_rev,
                    COALESCE(SUM(oi.item_cogs + oi.item_packaging_cost), 0) AS cogs,
                    COALESCE(SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee + oi.item_shipping_seller), 0) AS fees,
                    COALESCE(SUM(oi.item_return_loss), 0) AS ret_loss
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE o.dataset_id = ? AND o.order_month = ? {chan_clause}
                """,
                [dataset_id, ym] + chan_param,
            ).fetchone()
        )
        ad_r = conn.execute(
            f"SELECT COALESCE(SUM(m.ad_spend), 0) AS ad_spend FROM marketing_daily m WHERE m.dataset_id = ? AND m.spend_month = ? {m_chan_clause}",
            [dataset_id, ym] + chan_param,
        ).fetchone()
        r["ads"] = float(ad_r["ad_spend"]) if ad_r else 0.0
        r["net_profit"] = r["net_rev"] - r["cogs"] - r["fees"] - r["ret_loss"] - r["ads"]
        return {k: float(v) for k, v in r.items()}

    p0 = _month_snapshot(prev_m)
    p1 = _month_snapshot(curr_m)

    q0 = max(1.0, p0["qty"])
    q1 = max(1.0, p1["qty"])
    gm0_per_unit = (p0["net_rev"] - p0["cogs"]) / q0
    gross_price0 = p0["gross"] / q0
    gross_price1 = p1["gross"] / q1
    disc_per_unit0 = p0["disc"] / q0
    disc_per_unit1 = p1["disc"] / q1
    cogs_per_unit0 = p0["cogs"] / q0
    cogs_per_unit1 = p1["cogs"] / q1

    # Exact decomposition of Gross Profit change (GP1 - GP0):
    # GP = Q * (GrossPrice - Disc - UnitCOGS)
    volume_effect = (q1 - q0) * gm0_per_unit
    voucher_effect = -q1 * (disc_per_unit1 - disc_per_unit0)
    mix_and_cost_effect = q1 * ((gross_price1 - gross_price0) - (cogs_per_unit1 - cogs_per_unit0))
    fee_effect = -(p1["fees"] - p0["fees"])
    return_effect = -(p1["ret_loss"] - p0["ret_loss"])
    ads_effect = -(p1["ads"] - p0["ads"])

    steps = [
        {"label": f"Lãi Ròng {prev_m}", "value": round(p0["net_profit"]), "type": "start"},
        {"label": "Tác Động Sản Lượng (Volume)", "value": round(volume_effect), "type": "delta"},
        {"label": "Trợ Giá / Voucher Shop", "value": round(voucher_effect), "type": "delta"},
        {"label": "Cơ Cấu Hàng & Giá Vốn (Mix)", "value": round(mix_and_cost_effect), "type": "delta"},
        {"label": "Phí Sàn & Affiliate", "value": round(fee_effect), "type": "delta"},
        {"label": "Thiệt Hại Đơn Hoàn", "value": round(return_effect), "type": "delta"},
        {"label": "Chi Phí Ads Tăng/Giảm", "value": round(ads_effect), "type": "delta"},
        {"label": f"Lãi Ròng {curr_m}", "value": round(p1["net_profit"]), "type": "end"},
    ]

    delta_profit = p1["net_profit"] - p0["net_profit"]
    delta_rev_pct = ((p1["net_rev"] - p0["net_rev"]) / p0["net_rev"] * 100.0) if p0["net_rev"] > 0 else 0.0
    delta_prof_pct = (delta_profit / abs(p0["net_profit"]) * 100.0) if p0["net_profit"] != 0 else 0.0

    insights = [
        f"So với {prev_m}, doanh thu thuần {curr_m} biến động {delta_rev_pct:+.1f}% trong khi Lãi ròng thực biến động {delta_prof_pct:+.1f}% ({delta_profit:+,.0f} đ)."
    ]
    drivers = [
        ("Sản lượng bán", volume_effect),
        ("Mức chi Voucher trợ giá", voucher_effect),
        ("Cơ cấu mặt hàng (Mix)", mix_and_cost_effect),
        ("Phí sàn & Hoa hồng Affiliate", fee_effect),
        ("Thiệt hại đơn hoàn", return_effect),
        ("Chi phí chạy Ads", ads_effect),
    ]
    worst_driver = min(drivers, key=lambda x: x[1])
    best_driver = max(drivers, key=lambda x: x[1])
    if best_driver[1] > 0:
        insights.append(f"Động lực kéo lãi lên mạnh nhất: {best_driver[0]} đóng góp +{best_driver[1]:,.0f} đ.")
    if worst_driver[1] < 0:
        insights.append(f"Lỗ hổng bào mòn lợi nhuận lớn nhất: {worst_driver[0]} làm giảm {worst_driver[1]:,.0f} đ.")

    return {
        "available": True,
        "prev_month": prev_m,
        "curr_month": curr_m,
        "prev_profit": round(p0["net_profit"]),
        "curr_profit": round(p1["net_profit"]),
        "delta_profit": round(delta_profit),
        "delta_profit_pct": round(delta_prof_pct, 2),
        "steps": steps,
        "insights": insights,
    }


def get_rfm_cohort_and_optimizer(
    dataset_id: str,
    budget_vnd: float = 15_000_000,
) -> dict[str, Any]:
    with get_connection(readonly=True) as conn:
        max_dt_row = conn.execute(
            "SELECT MAX(order_date) AS max_dt FROM orders WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        ref_date_str = max_dt_row["max_dt"] if (max_dt_row and max_dt_row["max_dt"]) else "2026-10-31"
        ref_dt = datetime.strptime(ref_date_str[:10], "%Y-%m-%d").date()

        # 1. SQL Window Function RFM Scoring (NTILE(5))
        rfm_rows = conn.execute(
            """
            WITH cust_metrics AS (
                SELECT
                    c.customer_id,
                    c.customer_name,
                    c.phone_masked,
                    c.city,
                    c.acquisition_channel,
                    c.acquisition_cost,
                    CAST(julianday(:ref_date) - julianday(MAX(CASE WHEN o.status = 'COMPLETED' THEN o.order_date END)) AS INTEGER) AS recency_days,
                    COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) AS frequency,
                    COUNT(DISTINCT CASE WHEN o.status = 'RETURNED' THEN o.order_id END) AS return_orders,
                    COALESCE(SUM(oi.item_net_revenue), 0) AS net_revenue,
                    COALESCE(SUM(
                        oi.item_net_revenue - oi.item_cogs - oi.item_packaging_cost
                        - oi.item_platform_fee - oi.item_payment_fee - oi.item_affiliate_fee
                        - oi.item_shipping_seller - oi.item_return_loss
                    ), 0) AS contribution_profit
                FROM customers c
                JOIN orders o ON o.dataset_id = c.dataset_id AND o.customer_id = c.customer_id
                JOIN order_items oi ON oi.dataset_id = o.dataset_id AND oi.order_id = o.order_id
                WHERE c.dataset_id = :ds_id
                GROUP BY c.customer_id, c.customer_name, c.phone_masked, c.city, c.acquisition_channel, c.acquisition_cost
                HAVING COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) >= 1
            ),
            scored AS (
                SELECT
                    *,
                    NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
                    NTILE(5) OVER (ORDER BY frequency ASC, net_revenue ASC) AS f_score,
                    NTILE(5) OVER (ORDER BY net_revenue ASC) AS m_score
                FROM cust_metrics
            )
            SELECT * FROM scored
            ORDER BY contribution_profit DESC
            """,
            {"ds_id": dataset_id, "ref_date": ref_dt.isoformat()},
        ).fetchall()

        segments_agg: dict[str, dict[str, Any]] = {}
        candidates: list[dict[str, Any]] = []
        total_ltv_profit = 0.0
        total_cac = 0.0

        for row in rfm_rows:
            r = dict(row)
            r_sc, f_sc, m_sc = int(r["r_score"]), int(r["f_score"]), int(r["m_score"])
            rec = int(r["recency_days"] or 0)
            freq = int(r["frequency"])
            ret_cnt = int(r["return_orders"])
            net_rev = float(r["net_revenue"])
            c_prof = float(r["contribution_profit"])
            cac = float(r["acquisition_cost"])
            total_ltv_profit += c_prof
            total_cac += cac

            if c_prof <= 0 or (ret_cnt >= 2 and ret_cnt >= freq):
                seg_key = "LOW_MARGIN"
                seg_name = "🩸 Săn Sale / Hoàn Cao"
            elif r_sc >= 4 and f_sc >= 4 and m_sc >= 4:
                seg_key = "CHAMPIONS"
                seg_name = "💎 VIP Champions"
            elif rec > 48 and (f_sc >= 3 or m_sc >= 4):
                seg_key = "AT_RISK_VIP"
                seg_name = "⚠️ VIP Nguy Cơ Rời Bỏ"
            elif r_sc >= 3 and f_sc >= 3:
                seg_key = "LOYAL"
                seg_name = "🌿 Khách Quen Trung Thành"
            elif rec <= 40 and freq <= 2:
                seg_key = "PROMISING_NEW"
                seg_name = "🚀 Khách Mới Tiềm Năng"
            else:
                seg_key = "HIBERNATING"
                seg_name = "😴 Ngủ Đông (Hibernating)"

            bucket = segments_agg.setdefault(
                seg_key,
                {
                    "segment_key": seg_key,
                    "segment_name": seg_name,
                    "customer_count": 0,
                    "net_revenue": 0.0,
                    "contribution_profit": 0.0,
                    "total_cac": 0.0,
                    "recency_sum": 0,
                    "freq_sum": 0,
                },
            )
            bucket["customer_count"] += 1
            bucket["net_revenue"] += net_rev
            bucket["contribution_profit"] += c_prof
            bucket["total_cac"] += cac
            bucket["recency_sum"] += rec
            bucket["freq_sum"] += freq

            # Build Retention Campaign Candidate if positive expected ROI
            avg_order_rev = net_rev / max(1, freq)
            avg_order_margin = max(25000.0, c_prof / max(1, freq))
            if seg_key == "AT_RISK_VIP":
                action = "Zalo ZNS Cá Nhân Hóa + Voucher VIP 10% (Kéo quay lại)"
                voucher_cost = round(min(65000.0, avg_order_rev * 0.09), -2)
                msg_cost = 1500.0
                win_prob = 0.34
            elif seg_key == "PROMISING_NEW":
                action = "Ưu Đãi Mua Lần 2 Trong 30 Ngày (Freeship + Giảm 25k)"
                voucher_cost = 25000.0
                msg_cost = 1200.0
                win_prob = 0.27
            elif seg_key == "LOYAL":
                action = "Gợi Ý Combo Cross-Sell Kênh Web/Zalo (Không mất phí sàn)"
                voucher_cost = 20000.0
                msg_cost = 1000.0
                win_prob = 0.29
            elif seg_key == "HIBERNATING" and avg_order_margin > 65000:
                action = "Chiến Dịch Đánh Thức Khách Cũ (Voucher 35k Đơn Từ 299k)"
                voucher_cost = 35000.0
                msg_cost = 1200.0
                win_prob = 0.16
            else:
                continue

            # Campaign cost = direct message cost + expected redeemed voucher cost
            expected_campaign_cost = msg_cost + win_prob * voucher_cost
            # Incremental net profit = win_prob * (expected order margin - voucher_cost) - msg_cost
            expected_inc_profit = win_prob * (avg_order_margin - voucher_cost) - msg_cost
            expected_inc_rev = win_prob * avg_order_rev

            if expected_inc_profit > 5000 and expected_campaign_cost > 0:
                roi_ratio = expected_inc_profit / expected_campaign_cost
                candidates.append(
                    {
                        "customer_id": r["customer_id"],
                        "customer_name": r["customer_name"],
                        "phone_masked": r["phone_masked"],
                        "city": r["city"],
                        "segment_key": seg_key,
                        "segment_name": seg_name,
                        "recency_days": rec,
                        "frequency": freq,
                        "historical_revenue": round(net_rev),
                        "historical_profit": round(c_prof),
                        "rfm_code": f"{r_sc}{f_sc}{m_sc}",
                        "campaign_action": action,
                        "budget_cost": round(expected_campaign_cost),
                        "winback_prob_pct": round(win_prob * 100, 1),
                        "expected_inc_revenue": round(expected_inc_rev),
                        "expected_inc_profit": round(expected_inc_profit),
                        "roi_multiple": round(roi_ratio, 2),
                    }
                )

        total_custs = max(1, len(rfm_rows))
        segments_list = []
        order_priority = ["CHAMPIONS", "LOYAL", "AT_RISK_VIP", "PROMISING_NEW", "HIBERNATING", "LOW_MARGIN"]
        for sk in order_priority:
            if sk not in segments_agg:
                continue
            b = segments_agg[sk]
            cnt = max(1, b["customer_count"])
            segments_list.append(
                {
                    "segment_key": sk,
                    "segment_name": b["segment_name"],
                    "customer_count": b["customer_count"],
                    "share_pct": round(b["customer_count"] / total_custs * 100.0, 1),
                    "net_revenue": round(b["net_revenue"]),
                    "contribution_profit": round(b["contribution_profit"]),
                    "avg_recency_days": round(b["recency_sum"] / cnt, 1),
                    "avg_frequency": round(b["freq_sum"] / cnt, 2),
                    "avg_ltv_profit": round(b["contribution_profit"] / cnt),
                    "avg_cac": round(b["total_cac"] / cnt),
                    "ltv_cac_ratio": round(b["contribution_profit"] / max(1.0, b["total_cac"]), 2),
                }
            )

        # 2. Monthly Cohort Retention Matrix (SQL CTE)
        cohort_rows = conn.execute(
            """
            WITH first_comp AS (
                SELECT
                    customer_id,
                    MIN(order_month) AS cohort_month
                FROM orders
                WHERE dataset_id = ? AND status = 'COMPLETED'
                GROUP BY customer_id
            ),
            monthly_act AS (
                SELECT
                    fc.cohort_month,
                    o.order_month,
                    (CAST(substr(o.order_month, 1, 4) AS INTEGER) - CAST(substr(fc.cohort_month, 1, 4) AS INTEGER)) * 12
                    + (CAST(substr(o.order_month, 6, 2) AS INTEGER) - CAST(substr(fc.cohort_month, 6, 2) AS INTEGER)) AS month_index,
                    COUNT(DISTINCT o.customer_id) AS active_customers,
                    SUM(
                        oi.item_net_revenue - oi.item_cogs - oi.item_packaging_cost
                        - oi.item_platform_fee - oi.item_payment_fee - oi.item_affiliate_fee
                        - oi.item_shipping_seller - oi.item_return_loss
                    ) AS cohort_profit
                FROM first_comp fc
                JOIN orders o ON o.dataset_id = ? AND o.customer_id = fc.customer_id AND o.status = 'COMPLETED'
                JOIN order_items oi ON oi.dataset_id = o.dataset_id AND oi.order_id = o.order_id
                GROUP BY fc.cohort_month, o.order_month
            ),
            cohort_sizes AS (
                SELECT
                    fc.cohort_month,
                    COUNT(*) AS cohort_size,
                    AVG(c.acquisition_cost) AS avg_cac
                FROM first_comp fc
                JOIN customers c ON c.dataset_id = ? AND c.customer_id = fc.customer_id
                GROUP BY fc.cohort_month
            )
            SELECT
                cs.cohort_month,
                cs.cohort_size,
                cs.avg_cac,
                ma.month_index,
                ma.active_customers,
                ma.cohort_profit
            FROM cohort_sizes cs
            JOIN monthly_act ma ON ma.cohort_month = cs.cohort_month
            WHERE ma.month_index >= 0 AND ma.month_index <= 5
            ORDER BY cs.cohort_month ASC, ma.month_index ASC
            """,
            (dataset_id, dataset_id, dataset_id),
        ).fetchall()

        cohorts_map: dict[str, dict[str, Any]] = {}
        for cr in cohort_rows:
            cm = cr["cohort_month"]
            entry = cohorts_map.setdefault(
                cm,
                {
                    "cohort_month": cm,
                    "cohort_size": int(cr["cohort_size"]),
                    "avg_cac": round(float(cr["avg_cac"] or 0)),
                    "retention": {},
                    "cum_ltv_profit": 0.0,
                },
            )
            m_idx = int(cr["month_index"])
            ret_pct = round(int(cr["active_customers"]) / max(1, int(cr["cohort_size"])) * 100.0, 1)
            entry["retention"][f"M{m_idx}"] = ret_pct
            entry["cum_ltv_profit"] += float(cr["cohort_profit"] or 0.0) / max(1, int(cr["cohort_size"]))

        cohort_matrix = []
        for cm, entry in cohorts_map.items():
            entry["cum_ltv_profit"] = round(entry["cum_ltv_profit"])
            entry["payback_ratio"] = round(entry["cum_ltv_profit"] / max(1, entry["avg_cac"]), 2)
            cohort_matrix.append(entry)

        # 3. Greedy Knapsack Retention Budget Allocation
        candidates.sort(key=lambda x: (x["roi_multiple"], x["expected_inc_profit"]), reverse=True)
        selected_targets = []
        spent = 0.0
        inc_rev_sum = 0.0
        inc_prof_sum = 0.0
        seg_alloc: dict[str, int] = {}

        for cand in candidates:
            cost = float(cand["budget_cost"])
            if spent + cost <= budget_vnd:
                spent += cost
                inc_rev_sum += float(cand["expected_inc_revenue"])
                inc_prof_sum += float(cand["expected_inc_profit"])
                seg_alloc[cand["segment_name"]] = seg_alloc.get(cand["segment_name"], 0) + 1
                selected_targets.append(cand)

    return {
        "reference_date": ref_dt.isoformat(),
        "summary": {
            "active_customers": len(rfm_rows),
            "avg_ltv_profit": round(total_ltv_profit / total_custs),
            "avg_cac": round(total_cac / total_custs),
            "blended_ltv_cac": round(total_ltv_profit / max(1.0, total_cac), 2),
        },
        "segments": segments_list,
        "cohort_matrix": cohort_matrix,
        "optimizer": {
            "budget_limit": round(budget_vnd),
            "budget_used": round(spent),
            "customers_selected": len(selected_targets),
            "eligible_pool": len(candidates),
            "projected_incremental_revenue": round(inc_rev_sum),
            "projected_incremental_net_profit": round(inc_prof_sum),
            "net_roi_pct": round((inc_prof_sum / spent * 100.0) if spent > 0 else 0.0, 1),
            "segment_breakdown": [{"segment": k, "count": v} for k, v in seg_alloc.items()],
            "top_targets": selected_targets[:120],
        },
    }


def get_inventory_abc_xyz(dataset_id: str) -> dict[str, Any]:
    with get_connection(readonly=True) as conn:
        date_bounds = conn.execute(
            "SELECT MIN(order_date) AS min_d, MAX(order_date) AS max_d FROM orders WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if not date_bounds or not date_bounds["max_d"]:
            return {"items": [], "matrix": {}, "summary": {}}

        min_dt = datetime.strptime(date_bounds["min_d"][:10], "%Y-%m-%d").date()
        max_dt = datetime.strptime(date_bounds["max_d"][:10], "%Y-%m-%d").date()
        span_days = max(1, (max_dt - min_dt).days + 1)
        recent_cutoff = (max_dt - pd.Timedelta(days=44)).isoformat()

        skus_df = pd.read_sql_query(
            "SELECT * FROM skus WHERE dataset_id = ?",
            conn,
            params=(dataset_id,),
        )
        daily_df = pd.read_sql_query(
            """
            SELECT
                o.order_date,
                oi.sku_code,
                SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END) AS qty,
                SUM(oi.item_net_revenue) AS net_rev,
                SUM(oi.item_net_revenue - oi.item_cogs - oi.item_packaging_cost) AS gross_profit
            FROM order_items oi
            JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
            WHERE o.dataset_id = ?
            GROUP BY o.order_date, oi.sku_code
            """,
            conn,
            params=(dataset_id,),
        )

    all_days = pd.date_range(min_dt, max_dt, freq="D")
    num_weeks = max(1, len(all_days) // 7)

    # Compute ABC based on cumulative positive Gross Profit (or Net Revenue fallback)
    sku_records = []
    for _, s in skus_df.iterrows():
        code = s["sku_code"]
        sub = daily_df[daily_df["sku_code"] == code]
        total_qty = int(sub["qty"].sum()) if not sub.empty else 0
        total_rev = float(sub["net_rev"].sum()) if not sub.empty else 0.0
        total_gp = max(0.0, float(sub["gross_profit"].sum())) if not sub.empty else 0.0

        # Recent 45-day run-rate for responsive replenishment
        rec_sub = sub[sub["order_date"] >= recent_cutoff] if not sub.empty else sub
        rec_days = min(45, span_days)
        recent_daily_mean = float(rec_sub["qty"].sum()) / max(1, rec_days) if not rec_sub.empty else 0.0
        overall_daily_mean = total_qty / span_days
        avg_daily = 0.65 * recent_daily_mean + 0.35 * overall_daily_mean

        # Build complete daily series to compute true demand std & weekly CV
        if not sub.empty:
            s_series = sub.set_index(pd.to_datetime(sub["order_date"]))["qty"].reindex(all_days, fill_value=0).astype(float)
            std_daily = float(s_series.std(ddof=0))
            weekly = s_series.resample("7D").sum()
            w_mean = float(weekly.mean())
            cv_weekly = float(weekly.std(ddof=0) / w_mean) if w_mean > 0 else 9.99
        else:
            std_daily = 0.0
            cv_weekly = 9.99

        sku_records.append(
            {
                "sku_code": code,
                "product_name": s["product_name"],
                "category": s["category"],
                "list_price": float(s["list_price"]),
                "unit_cogs": float(s["unit_cogs"]),
                "current_stock": int(s["current_stock"]),
                "lead_time_days": int(s["lead_time_days"]),
                "min_order_qty": int(s["min_order_qty"]),
                "total_qty": total_qty,
                "net_revenue": total_rev,
                "gross_profit_pos": total_gp,
                "avg_daily_demand": avg_daily,
                "std_daily_demand": std_daily,
                "cv_weekly": cv_weekly,
            }
        )

    sku_records.sort(key=lambda x: x["gross_profit_pos"], reverse=True)
    gp_sum = sum(x["gross_profit_pos"] for x in sku_records) or 1.0
    cum_share = 0.0

    matrix_counts: dict[str, dict[str, Any]] = {
        f"{a}{x}": {"cell": f"{a}{x}", "sku_count": 0, "stock_value": 0, "skus": []}
        for a in ("A", "B", "C")
        for x in ("X", "Y", "Z")
    }

    total_stock_value = 0.0
    dead_stock_value = 0.0
    stockout_risk_count = 0
    total_reorder_budget = 0.0
    enriched_items = []

    for rec in sku_records:
        prev_share = cum_share
        cum_share += rec["gross_profit_pos"] / gp_sum
        if prev_share < 0.78:
            abc = "A"
            z_service = 1.645  # 95% service level
            target_cover_days = 28
        elif prev_share < 0.94:
            abc = "B"
            z_service = 1.282  # 90% service level
            target_cover_days = 21
        else:
            abc = "C"
            z_service = 1.036  # 85% service level
            target_cover_days = 14

        cv = rec["cv_weekly"]
        if cv <= 0.42:
            xyz = "X"
        elif cv <= 0.80:
            xyz = "Y"
        else:
            xyz = "Z"

        cell = f"{abc}{xyz}"
        lt = max(1, rec["lead_time_days"])
        avg_d = rec["avg_daily_demand"]
        std_d = rec["std_daily_demand"]
        stock = rec["current_stock"]
        unit_cogs = rec["unit_cogs"]
        stock_val = stock * unit_cogs
        total_stock_value += stock_val

        safety_stock = int(math.ceil(z_service * std_d * math.sqrt(lt)))
        rop = int(math.ceil(avg_d * lt + safety_stock))
        doi = (stock / avg_d) if avg_d > 0.02 else 999.0

        if doi < lt:
            status = "STOCKOUT_RISK"
            status_label = "🚨 Đứt Hàng Sắp Xảy Ra"
            stockout_risk_count += 1
        elif stock <= rop:
            status = "REORDER_SOON"
            status_label = "⚠️ Chạm Điểm Đặt Hàng (ROP)"
        elif doi > 75:
            status = "OVERSTOCK_DEAD"
            status_label = "🧊 Đọng Vốn / Chậm Luân Chuyển"
            dead_stock_value += stock_val
        else:
            status = "HEALTHY"
            status_label = "✅ Tồn Kho Tối Ưu"

        if status in ("STOCKOUT_RISK", "REORDER_SOON"):
            target_stock = int(math.ceil(avg_d * (lt + target_cover_days) + safety_stock))
            raw_order = max(rec["min_order_qty"], target_stock - stock)
            suggested_order_qty = int(math.ceil(raw_order / 5.0) * 5)
            reorder_cost = suggested_order_qty * unit_cogs
            total_reorder_budget += reorder_cost
            action_text = f"Đặt nhập ngay {suggested_order_qty} sp (Lead time {lt} ngày)"
        elif status == "OVERSTOCK_DEAD":
            suggested_order_qty = 0
            reorder_cost = 0.0
            action_text = "Ngừng nhập; xả kho Flash Sale / ghép Bundle thu hồi vốn"
        else:
            suggested_order_qty = 0
            reorder_cost = 0.0
            action_text = f"An toàn — theo dõi định kỳ ({doi:.0f} ngày đủ bán)"

        matrix_counts[cell]["sku_count"] += 1
        matrix_counts[cell]["stock_value"] += round(stock_val)
        matrix_counts[cell]["skus"].append(rec["sku_code"])

        enriched_items.append(
            {
                "sku_code": rec["sku_code"],
                "product_name": rec["product_name"],
                "category": rec["category"],
                "abc_xyz": cell,
                "abc": abc,
                "xyz": xyz,
                "current_stock": stock,
                "avg_daily_demand": round(avg_d, 2),
                "cv_weekly": round(cv, 2),
                "lead_time_days": lt,
                "safety_stock": safety_stock,
                "reorder_point": rop,
                "days_of_inventory": round(min(999.0, doi), 1),
                "stock_value_vnd": round(stock_val),
                "suggested_order_qty": suggested_order_qty,
                "reorder_budget_vnd": round(reorder_cost),
                "status": status,
                "status_label": status_label,
                "action_text": action_text,
            }
        )

    # Order urgent stockouts first, then overstock capital traps
    priority_map = {"STOCKOUT_RISK": 0, "REORDER_SOON": 1, "OVERSTOCK_DEAD": 2, "HEALTHY": 3}
    enriched_items.sort(key=lambda x: (priority_map[x["status"]], -x["stock_value_vnd"]))

    return {
        "summary": {
            "total_skus": len(enriched_items),
            "total_stock_value_vnd": round(total_stock_value),
            "dead_stock_value_vnd": round(dead_stock_value),
            "dead_stock_share_pct": round(dead_stock_value / max(1.0, total_stock_value) * 100.0, 1),
            "stockout_risk_skus": stockout_risk_count,
            "total_reorder_budget_vnd": round(total_reorder_budget),
        },
        "matrix": matrix_counts,
        "items": enriched_items,
    }


def simulate_what_if(
    dataset_id: str,
    sku_code: str = "ALL",
    channel: str = "ALL",
    price_change_pct: float = 0.0,
    voucher_change_pts: float = 0.0,
    platform_fee_change_pts: float = 0.0,
    return_rate_change_pts: float = 0.0,
    cogs_change_pct: float = 0.0,
    ads_change_pct: float = 0.0,
    elasticity_override: float | None = None,
) -> dict[str, Any]:
    """
    Elastic Unit-Economics & Break-Even Simulator with Price Optimization Curve.
    """
    clauses = ["o.dataset_id = ?"]
    params: list[Any] = [dataset_id]
    m_clauses = ["m.dataset_id = ?"]
    m_params: list[Any] = [dataset_id]

    if channel and channel != "ALL":
        clauses.append("o.channel = ?")
        params.append(channel)
        m_clauses.append("m.channel = ?")
        m_params.append(channel)
    if sku_code and sku_code != "ALL":
        clauses.append("oi.sku_code = ?")
        params.append(sku_code)
        m_clauses.append("m.sku_code = ?")
        m_params.append(sku_code)

    where_sql = " AND ".join(clauses)
    m_where_sql = " AND ".join(m_clauses)

    with get_connection(readonly=True) as conn:
        base = dict(
            conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END), 0) AS units,
                    COALESCE(SUM(CASE WHEN o.status = 'RETURNED' THEN oi.quantity ELSE 0 END), 0) AS ret_units,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_gross ELSE 0 END), 0) AS gross_rev,
                    COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.item_seller_discount ELSE 0 END), 0) AS seller_disc,
                    COALESCE(SUM(oi.item_net_revenue), 0) AS net_rev,
                    COALESCE(SUM(oi.item_cogs), 0) AS cogs,
                    COALESCE(SUM(oi.item_packaging_cost), 0) AS pack_cost,
                    COALESCE(SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee), 0) AS pct_fees,
                    COALESCE(SUM(oi.item_shipping_seller), 0) AS ship_seller,
                    COALESCE(SUM(oi.item_return_loss), 0) AS ret_loss
                FROM order_items oi
                JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
                WHERE {where_sql}
                """,
                params,
            ).fetchone()
        )
        ads_row = conn.execute(
            f"SELECT COALESCE(SUM(m.ad_spend), 0) AS ad_spend FROM marketing_daily m WHERE {m_where_sql}",
            m_params,
        ).fetchone()
        base_ads = float(ads_row["ad_spend"]) if ads_row else 0.0

        if sku_code and sku_code != "ALL":
            el_row = conn.execute(
                "SELECT price_elasticity FROM skus WHERE dataset_id = ? AND sku_code = ?",
                (dataset_id, sku_code),
            ).fetchone()
            default_elasticity = float(el_row["price_elasticity"]) if el_row else -1.35
        else:
            el_row = conn.execute(
                "SELECT AVG(price_elasticity) AS avg_el FROM skus WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            default_elasticity = float(el_row["avg_el"]) if (el_row and el_row["avg_el"]) else -1.35

    elasticity = float(elasticity_override) if elasticity_override is not None else default_elasticity

    q0 = max(1.0, float(base["units"]))
    gross0 = float(base["gross_rev"])
    disc0 = float(base["seller_disc"])
    net_rev0 = float(base["net_rev"])
    cogs0 = float(base["cogs"])
    pack0 = float(base["pack_cost"])
    fees0 = float(base["pct_fees"])
    ship0 = float(base["ship_seller"])
    ret_loss0 = float(base["ret_loss"])
    ret_units0 = float(base["ret_units"])

    unit_gross0 = gross0 / q0
    disc_rate0 = disc0 / gross0 if gross0 > 0 else 0.0
    fee_rate0 = fees0 / net_rev0 if net_rev0 > 0 else 0.0
    unit_cogs0 = cogs0 / q0
    unit_pack0 = pack0 / q0
    unit_ship0 = ship0 / q0
    shipped_u0 = q0 + ret_units0
    ret_rate0 = ret_units0 / shipped_u0 if shipped_u0 > 0 else 0.05
    loss_per_ret_unit = (ret_loss0 / ret_units0) if ret_units0 > 0 else (unit_pack0 + 24000.0 + unit_cogs0 * 0.12)

    base_contrib_total = net_rev0 - cogs0 - pack0 - fees0 - ship0 - ret_loss0
    base_net_profit = base_contrib_total - base_ads
    base_unit_contrib = base_contrib_total / q0

    def _eval_scenario(p_chg_pct: float) -> dict[str, float]:
        unit_gross1 = unit_gross0 * (1.0 + p_chg_pct / 100.0)
        disc_rate1 = float(np.clip(disc_rate0 + voucher_change_pts / 100.0, 0.0, 0.70))
        unit_net_price1 = unit_gross1 * (1.0 - disc_rate1)
        unit_net_price0 = max(1.0, unit_gross0 * (1.0 - disc_rate0))

        # Effective realized buyer price change drives elastic volume response
        eff_price_rel_change = (unit_net_price1 - unit_net_price0) / unit_net_price0
        # Add modest ad-driven volume lift (diminishing square-root return)
        ad_vol_mult = (1.0 + ads_change_pct / 100.0) ** 0.22 if ads_change_pct > -95 else 0.75
        vol_mult = max(0.15, (1.0 + elasticity * eff_price_rel_change) * ad_vol_mult)
        q1 = q0 * vol_mult

        fee_rate1 = float(np.clip(fee_rate0 + platform_fee_change_pts / 100.0, 0.0, 0.65))
        ret_rate1 = float(np.clip(ret_rate0 + return_rate_change_pts / 100.0, 0.0, 0.60))
        unit_cogs1 = unit_cogs0 * (1.0 + cogs_change_pct / 100.0)

        # Expected return loss per completed unit = (ret_rate1 / (1 - ret_rate1)) * loss_per_ret_unit
        ret_burden_per_comp_unit = (ret_rate1 / max(0.1, 1.0 - ret_rate1)) * loss_per_ret_unit
        unit_fee1 = unit_net_price1 * fee_rate1
        unit_contrib1 = unit_net_price1 - unit_cogs1 - unit_pack0 - unit_fee1 - unit_ship0 - ret_burden_per_comp_unit

        sim_net_rev = q1 * unit_net_price1
        sim_contrib_total = q1 * unit_contrib1
        sim_ads = base_ads * max(0.0, 1.0 + ads_change_pct / 100.0)
        sim_net_profit = sim_contrib_total - sim_ads
        return {
            "units": q1,
            "unit_net_price": unit_net_price1,
            "unit_contrib": unit_contrib1,
            "net_revenue": sim_net_rev,
            "contrib_total": sim_contrib_total,
            "ads": sim_ads,
            "net_profit": sim_net_profit,
            "net_margin_pct": (sim_net_profit / sim_net_rev * 100.0) if sim_net_rev > 0 else 0.0,
        }

    sim = _eval_scenario(price_change_pct)
    unit_contrib1 = sim["unit_contrib"]
    sim_ads = sim["ads"]

    # Break-even units (to cover Ads spend) & Required Volume to Maintain Baseline Profit
    negative_unit_margin = unit_contrib1 <= 0
    if not negative_unit_margin:
        breakeven_units = math.ceil(sim_ads / unit_contrib1) if sim_ads > 0 else 0
        target_units_keep_profit = (base_net_profit + sim_ads) / unit_contrib1
        req_vol_change_pct = ((target_units_keep_profit - q0) / q0) * 100.0
    else:
        breakeven_units = None
        req_vol_change_pct = None

    # Generate Price Sensitivity Curve (-20% to +25% in 2.5% steps)
    curve = []
    for p_step in np.arange(-20.0, 27.5, 2.5):
        pt = _eval_scenario(float(p_step))
        curve.append(
            {
                "price_change_pct": round(float(p_step), 1),
                "units": round(pt["units"]),
                "net_revenue": round(pt["net_revenue"]),
                "net_profit": round(pt["net_profit"]),
            }
        )
    optimal_point = max(curve, key=lambda x: x["net_profit"])

    return {
        "elasticity_used": round(elasticity, 2),
        "negative_unit_margin": negative_unit_margin,
        "baseline": {
            "units": round(q0),
            "unit_net_price": round(net_rev0 / q0),
            "unit_contribution": round(base_unit_contrib),
            "net_revenue": round(net_rev0),
            "ad_spend": round(base_ads),
            "net_profit": round(base_net_profit),
            "net_margin_pct": round((base_net_profit / net_rev0 * 100.0) if net_rev0 > 0 else 0.0, 2),
        },
        "simulated": {
            "units": round(sim["units"]),
            "units_change_pct": round((sim["units"] - q0) / q0 * 100.0, 1),
            "unit_net_price": round(sim["unit_net_price"]),
            "unit_contribution": round(unit_contrib1),
            "net_revenue": round(sim["net_revenue"]),
            "ad_spend": round(sim_ads),
            "net_profit": round(sim["net_profit"]),
            "profit_delta": round(sim["net_profit"] - base_net_profit),
            "net_margin_pct": round(sim["net_margin_pct"], 2),
            "breakeven_units": breakeven_units,
            "required_vol_change_for_same_profit_pct": round(req_vol_change_pct, 1) if req_vol_change_pct is not None else None,
        },
        "optimal_price_suggestion": optimal_point,
        "sensitivity_curve": curve,
    }
