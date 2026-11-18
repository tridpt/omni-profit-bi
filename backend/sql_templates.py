"""
Curated Senior Data Analyst SQL Templates (CTEs, Window Functions, Funnel, Cohort, Pareto)
for the built-in Read-Only SQL Workbench.
"""

from __future__ import annotations
from typing import Any


def get_sql_templates(dataset_id: str) -> list[dict[str, Any]]:
    ds = dataset_id.replace("'", "''")
    return [
        {
            "id": "sku_true_pnl_cte",
            "title": "1. Bóc Tách Lãi Ròng Thực & Bẫy Doanh Thu Ảo Theo SKU (Multi-CTE)",
            "skill_tags": ["CTE", "LEFT JOIN", "Unit Economics", "CASE WHEN"],
            "business_question": "Mã hàng nào doanh số cao nhưng thực chất đang âm lợi nhuận ròng sau khi trừ giá vốn, phí sàn, Affiliate, đơn hoàn và Ads?",
            "sql": f"""-- Giải phẫu P&L thực tế từng SKU (kết hợp bảng đơn hàng, dòng hàng & chi phí Ads)
WITH sku_sales AS (
    SELECT
        oi.sku_code,
        SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END) AS sl_ban,
        ROUND(SUM(oi.item_net_revenue)) AS doanh_thu_thuan,
        ROUND(SUM(oi.item_cogs + oi.item_packaging_cost)) AS gia_von_dong_goi,
        ROUND(SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee + oi.item_shipping_seller)) AS tong_phi_kenh,
        ROUND(SUM(oi.item_return_loss)) AS lo_don_hoan
    FROM order_items oi
    JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
    WHERE oi.dataset_id = '{ds}'
    GROUP BY oi.sku_code
),
sku_ads AS (
    SELECT sku_code, ROUND(SUM(ad_spend)) AS chi_phi_ads
    FROM marketing_daily
    WHERE dataset_id = '{ds}'
    GROUP BY sku_code
)
SELECT
    s.sku_code,
    s.product_name,
    ss.sl_ban,
    ss.doanh_thu_thuan,
    ss.tong_phi_kenh,
    ss.lo_don_hoan,
    COALESCE(sa.chi_phi_ads, 0) AS chi_phi_ads,
    ROUND(ss.doanh_thu_thuan - ss.gia_von_dong_goi - ss.tong_phi_kenh - ss.lo_don_hoan - COALESCE(sa.chi_phi_ads, 0)) AS lai_rong_thuc,
    ROUND(
        (ss.doanh_thu_thuan - ss.gia_von_dong_goi - ss.tong_phi_kenh - ss.lo_don_hoan - COALESCE(sa.chi_phi_ads, 0))
        * 100.0 / NULLIF(ss.doanh_thu_thuan, 0), 2
    ) AS bien_lai_rong_pct
FROM skus s
JOIN sku_sales ss ON ss.sku_code = s.sku_code
LEFT JOIN sku_ads sa ON sa.sku_code = s.sku_code
WHERE s.dataset_id = '{ds}'
ORDER BY lai_rong_thuc ASC;""",
        },
        {
            "id": "pareto_window_80_20",
            "title": "2. Phân Tích Pareto 80/20 Đóng Góp Lợi Nhuận (SUM() OVER Window)",
            "skill_tags": ["Window Function", "Cumulative Share", "ABC Classification"],
            "business_question": "Top những SKU nào đang gánh 80% tổng lợi nhuận gộp của toàn cửa hàng (Nhóm A)?",
            "sql": f"""-- Tính tỷ trọng đóng góp tích lũy (Running Total) bằng Window Function
WITH sku_gp AS (
    SELECT
        sku_code,
        product_name,
        ROUND(SUM(contribution_profit_before_ads)) AS loi_nhuan_gop
    FROM vw_order_item_pnl
    WHERE dataset_id = '{ds}'
    GROUP BY sku_code, product_name
    HAVING loi_nhuan_gop > 0
),
ranked AS (
    SELECT
        sku_code,
        product_name,
        loi_nhuan_gop,
        ROUND(loi_nhuan_gop * 100.0 / SUM(loi_nhuan_gop) OVER (), 2) AS ty_trong_pct,
        ROUND(
            SUM(loi_nhuan_gop) OVER (ORDER BY loi_nhuan_gop DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            * 100.0 / SUM(loi_nhuan_gop) OVER (), 2
        ) AS tich_luy_pct
    FROM sku_gp
)
SELECT
    sku_code,
    product_name,
    loi_nhuan_gop,
    ty_trong_pct,
    tich_luy_pct,
    CASE
        WHEN tich_luy_pct <= 80 THEN 'A - Chủ lực (Top 80%)'
        WHEN tich_luy_pct <= 95 THEN 'B - Quan trọng (80-95%)'
        ELSE 'C - Đuôi dài (Bottom 5%)'
    END AS phan_hang_abc
FROM ranked
ORDER BY loi_nhuan_gop DESC;""",
        },
        {
            "id": "rfm_ntile_scoring",
            "title": "3. Chấm Điểm RFM Bằng Hàm Phân Vị NTILE(5) & Săn Khách VIP Sắp Rời Bỏ",
            "skill_tags": ["NTILE(5) OVER", "Julianday", "Customer Segmentation"],
            "business_question": "Những khách hàng từng chi tiêu lớn (M cao, F cao) nào đã quá 45 ngày chưa quay lại mua?",
            "sql": f"""-- Phân vị RFM 1-5 bằng SQL Window Function NTILE(5)
WITH ref AS (
    SELECT MAX(order_date) AS max_dt FROM orders WHERE dataset_id = '{ds}'
),
cust_base AS (
    SELECT
        o.customer_id,
        c.customer_name,
        c.city,
        CAST(julianday((SELECT max_dt FROM ref)) - julianday(MAX(o.order_date)) AS INTEGER) AS recency_days,
        COUNT(DISTINCT o.order_id) AS frequency,
        ROUND(SUM(oi.item_net_revenue)) AS monetary_vnd
    FROM orders o
    JOIN order_items oi ON oi.dataset_id = o.dataset_id AND oi.order_id = o.order_id
    JOIN customers c ON c.dataset_id = o.dataset_id AND c.customer_id = o.customer_id
    WHERE o.dataset_id = '{ds}' AND o.status = 'COMPLETED'
    GROUP BY o.customer_id, c.customer_name, c.city
),
rfm AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
        NTILE(5) OVER (ORDER BY frequency ASC, monetary_vnd ASC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary_vnd ASC) AS m_score
    FROM cust_base
)
SELECT
    customer_id,
    customer_name,
    city,
    recency_days,
    frequency,
    monetary_vnd,
    (r_score || '-' || f_score || '-' || m_score) AS rfm_tier
FROM rfm
WHERE recency_days >= 45 AND m_score >= 4
ORDER BY monetary_vnd DESC
LIMIT 30;""",
        },
        {
            "id": "repeat_lag_interval",
            "title": "4. Chu Kỳ Mua Lặp Lại Giữa Lần 1 & Lần 2 (LAG() OVER Window)",
            "skill_tags": ["LAG() OVER", "ROW_NUMBER()", "Lifecycle Timing"],
            "business_question": "Trung bình khách hàng mất bao nhiêu ngày để quay lại đặt đơn thứ 2 theo từng kênh bán?",
            "sql": f"""-- Dùng LAG() và ROW_NUMBER() tìm khoảng cách ngày giữa đơn thứ 1 và đơn thứ 2
WITH ordered_purchases AS (
    SELECT
        customer_id,
        channel,
        order_id,
        order_date,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date ASC, order_id ASC) AS order_seq,
        LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date ASC, order_id ASC) AS prev_order_date
    FROM orders
    WHERE dataset_id = '{ds}' AND status = 'COMPLETED'
)
SELECT
    channel AS kenh_mua_lan_2,
    COUNT(*) AS so_khach_mua_lai_lan_2,
    ROUND(AVG(julianday(order_date) - julianday(prev_order_date)), 1) AS tb_so_ngay_quay_lai,
    ROUND(MIN(julianday(order_date) - julianday(prev_order_date)), 0) AS nhanh_nhat_ngay,
    ROUND(MAX(julianday(order_date) - julianday(prev_order_date)), 0) AS lau_nhat_ngay
FROM ordered_purchases
WHERE order_seq = 2 AND prev_order_date IS NOT NULL
GROUP BY channel
ORDER BY tb_so_ngay_quay_lai ASC;""",
        },
        {
            "id": "cohort_retention_sql",
            "title": "5. Ma Trận Giữ Chân Khách Hàng Cohort Theo Tháng Gia Nhập",
            "skill_tags": ["Cohort Analysis", "Self-Join CTE", "Retention %"],
            "business_question": "Tệp khách mới của từng tháng còn giữ chân được bao nhiêu % sau 1, 2, 3 tháng?",
            "sql": f"""-- Phân tích Cohort Retention chuẩn Product / Growth Analytics
WITH first_month AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM orders
    WHERE dataset_id = '{ds}' AND status = 'COMPLETED'
    GROUP BY customer_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS new_customers
    FROM first_month
    GROUP BY cohort_month
),
activity AS (
    SELECT
        fm.cohort_month,
        (CAST(substr(o.order_month, 1, 4) AS INTEGER) - CAST(substr(fm.cohort_month, 1, 4) AS INTEGER)) * 12
        + (CAST(substr(o.order_month, 6, 2) AS INTEGER) - CAST(substr(fm.cohort_month, 6, 2) AS INTEGER)) AS m_idx,
        COUNT(DISTINCT o.customer_id) AS active_users
    FROM first_month fm
    JOIN orders o ON o.dataset_id = '{ds}' AND o.customer_id = fm.customer_id AND o.status = 'COMPLETED'
    GROUP BY fm.cohort_month, m_idx
)
SELECT
    cs.cohort_month,
    cs.new_customers AS quy_mo_cohort,
    ROUND(MAX(CASE WHEN a.m_idx = 0 THEN a.active_users * 100.0 / cs.new_customers END), 1) AS M0_pct,
    ROUND(MAX(CASE WHEN a.m_idx = 1 THEN a.active_users * 100.0 / cs.new_customers END), 1) AS M1_pct,
    ROUND(MAX(CASE WHEN a.m_idx = 2 THEN a.active_users * 100.0 / cs.new_customers END), 1) AS M2_pct,
    ROUND(MAX(CASE WHEN a.m_idx = 3 THEN a.active_users * 100.0 / cs.new_customers END), 1) AS M3_pct,
    ROUND(MAX(CASE WHEN a.m_idx = 4 THEN a.active_users * 100.0 / cs.new_customers END), 1) AS M4_pct
FROM cohort_size cs
JOIN activity a ON a.cohort_month = cs.cohort_month
GROUP BY cs.cohort_month, cs.new_customers
ORDER BY cs.cohort_month;""",
        },
        {
            "id": "channel_leakage_audit",
            "title": "6. Kiểm Toán Thất Thoát Phí Sàn, Affiliate & Đơn Hoàn Theo Kênh",
            "skill_tags": ["Channel Audit", "Return Rate", "Fee Burden %"],
            "business_question": "Kênh bán nào đang ngốn tỷ lệ phí + hoàn đơn cao nhất trên mỗi 100 đồng doanh thu?",
            "sql": f"""-- So sánh gánh nặng phí ẩn & hoàn đơn giữa các kênh bán hàng
SELECT
    o.channel,
    COUNT(DISTINCT o.order_id) AS tong_don,
    ROUND(
        COUNT(DISTINCT CASE WHEN o.status = 'RETURNED' THEN o.order_id END) * 100.0
        / NULLIF(COUNT(DISTINCT CASE WHEN o.status IN ('COMPLETED', 'RETURNED') THEN o.order_id END), 0), 2
    ) AS ty_le_hoan_pct,
    ROUND(SUM(oi.item_net_revenue)) AS doanh_thu_thuan,
    ROUND(SUM(oi.item_platform_fee + oi.item_payment_fee)) AS phi_san_tt,
    ROUND(SUM(oi.item_affiliate_fee)) AS phi_affiliate,
    ROUND(SUM(oi.item_return_loss)) AS thiet_hai_hoan_don,
    ROUND(
        SUM(oi.item_platform_fee + oi.item_payment_fee + oi.item_affiliate_fee + oi.item_return_loss)
        * 100.0 / NULLIF(SUM(oi.item_net_revenue), 0), 2
    ) AS ty_le_bao_mon_pct
FROM orders o
JOIN order_items oi ON oi.dataset_id = o.dataset_id AND oi.order_id = o.order_id
WHERE o.dataset_id = '{ds}'
GROUP BY o.channel
ORDER BY ty_le_bao_mon_pct DESC;""",
        },
        {
            "id": "double_day_cannibalization",
            "title": "7. Đánh Giá Hiệu Quả Ngày Đôi Mega Sale vs Ngày Thường (Promo Audit)",
            "skill_tags": ["Promo Uplift", "Margin Compression", "Date Pattern"],
            "business_question": "Vào các ngày Sale Đôi (6/6, 7/7, 8/8, 9/9, 10/10), đơn hàng tăng gấp mấy lần nhưng biên lợi nhuận bị nén bao nhiêu %?",
            "sql": f"""-- Kiểm tra xem ngày Sale lớn mang lại Lãi thực hay chỉ tăng GMV ảo
WITH daily_pnl AS (
    SELECT
        o.order_date,
        CASE
            WHEN substr(o.order_date, 6, 5) IN ('05-05','06-06','07-07','08-08','09-09','10-10','10-20')
            THEN 'Mega Sale / Ngày Đôi'
            ELSE 'Ngày Thường'
        END AS loai_ngay,
        COUNT(DISTINCT CASE WHEN o.status = 'COMPLETED' THEN o.order_id END) AS don_thanh_cong,
        SUM(oi.item_net_revenue) AS net_rev,
        SUM(
            oi.item_net_revenue - oi.item_cogs - oi.item_packaging_cost
            - oi.item_platform_fee - oi.item_payment_fee - oi.item_affiliate_fee
            - oi.item_shipping_seller - oi.item_return_loss
        ) AS contrib_before_ads
    FROM orders o
    JOIN order_items oi ON oi.dataset_id = o.dataset_id AND oi.order_id = o.order_id
    WHERE o.dataset_id = '{ds}'
    GROUP BY o.order_date
),
daily_ads AS (
    SELECT spend_date, SUM(ad_spend) AS ads
    FROM marketing_daily
    WHERE dataset_id = '{ds}'
    GROUP BY spend_date
)
SELECT
    dp.loai_ngay,
    COUNT(*) AS so_ngay,
    ROUND(AVG(dp.don_thanh_cong), 1) AS tb_don_moi_ngay,
    ROUND(AVG(dp.net_rev)) AS tb_doanh_thu_ngay,
    ROUND(AVG(dp.contrib_before_ads - COALESCE(da.ads, 0))) AS tb_lai_rong_ngay,
    ROUND(
        SUM(dp.contrib_before_ads - COALESCE(da.ads, 0)) * 100.0 / NULLIF(SUM(dp.net_rev), 0), 2
    ) AS bien_lai_rong_pct
FROM daily_pnl dp
LEFT JOIN daily_ads da ON da.spend_date = dp.order_date
GROUP BY dp.loai_ngay;""",
        },
        {
            "id": "inventory_runrate_alert",
            "title": "8. Cảnh Báo Đứt Hàng Dựa Trên Tốc Độ Bán 30 Ngày Gần Nhất",
            "skill_tags": ["Inventory DOI", "Run-Rate", "Supply Chain SQL"],
            "business_question": "Những SKU nào có số ngày tồn kho còn lại (DOI) thấp hơn thời gian chờ nhập hàng (Lead Time)?",
            "sql": f"""-- Đối chiếu Tồn kho hiện tại với tốc độ bán 30 ngày gần nhất và Lead Time nhà cung cấp
WITH max_d AS (
    SELECT date(MAX(order_date), '-29 days') AS cutoff_30d FROM orders WHERE dataset_id = '{ds}'
),
recent_velocity AS (
    SELECT
        oi.sku_code,
        SUM(CASE WHEN o.status = 'COMPLETED' THEN oi.quantity ELSE 0 END) / 30.0 AS toc_do_ban_ngay
    FROM order_items oi
    JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
    WHERE oi.dataset_id = '{ds}' AND o.order_date >= (SELECT cutoff_30d FROM max_d)
    GROUP BY oi.sku_code
)
SELECT
    s.sku_code,
    s.product_name,
    s.current_stock AS ton_hien_tai,
    ROUND(COALESCE(rv.toc_do_ban_ngay, 0), 2) AS ban_tb_ngay,
    ROUND(s.current_stock / NULLIF(rv.toc_do_ban_ngay, 0), 1) AS so_ngay_du_ban_doi,
    s.lead_time_days AS thoi_gian_cho_nhap,
    ROUND(s.current_stock * s.unit_cogs) AS gia_tri_ton_kho_vnd
FROM skus s
LEFT JOIN recent_velocity rv ON rv.sku_code = s.sku_code
WHERE s.dataset_id = '{ds}'
ORDER BY so_ngay_du_ban_doi ASC;""",
        },
        {
            "id": "market_basket_lift_sql",
            "title": "9. Phân Tích Giỏ Hàng & Hệ Số Kết Hợp Lift (Self-Join Association SQL)",
            "skill_tags": ["Self-Join", "Market Basket", "Support & Lift"],
            "business_question": "Những cặp sản phẩm nào khách hàng thực sự có xu hướng mua chung cao gấp nhiều lần ngẫu nhiên (Lift > 1.2) để ghép Combo?",
            "sql": f"""-- Dùng MATERIALIZED CTE & CROSS JOIN để tính Support, Confidence & Lift trong < 15ms
WITH tot AS MATERIALIZED (
    SELECT CAST(COUNT(DISTINCT order_id) AS REAL) AS n_orders
    FROM orders
    WHERE dataset_id = '{ds}' AND status = 'COMPLETED'
),
sku_freq AS MATERIALIZED (
    SELECT oi.sku_code, COUNT(DISTINCT oi.order_id) AS cnt
    FROM order_items oi
    JOIN orders o ON o.dataset_id = oi.dataset_id AND o.order_id = oi.order_id
    WHERE oi.dataset_id = '{ds}' AND o.status = 'COMPLETED'
    GROUP BY oi.sku_code
),
pairs AS MATERIALIZED (
    SELECT
        a.sku_code AS sku_a,
        b.sku_code AS sku_b,
        COUNT(DISTINCT a.order_id) AS co_orders
    FROM order_items a
    JOIN order_items b
      ON b.dataset_id = a.dataset_id
     AND b.order_id = a.order_id
     AND a.sku_code < b.sku_code
    JOIN orders o
      ON o.dataset_id = a.dataset_id
     AND o.order_id = a.order_id
    WHERE a.dataset_id = '{ds}' AND o.status = 'COMPLETED'
    GROUP BY a.sku_code, b.sku_code
    HAVING co_orders >= 5
)
SELECT
    p.sku_a,
    sa.product_name AS san_pham_a,
    p.sku_b,
    sb.product_name AS san_pham_b,
    p.co_orders AS so_don_mua_chung,
    ROUND(p.co_orders * 100.0 / t.n_orders, 2) AS support_pct,
    ROUND(p.co_orders * 100.0 / fa.cnt, 1) AS conf_a_sang_b_pct,
    ROUND((p.co_orders / t.n_orders) / ((fa.cnt / t.n_orders) * (fb.cnt / t.n_orders)), 2) AS he_so_lift
FROM pairs p
CROSS JOIN tot t
JOIN sku_freq fa ON fa.sku_code = p.sku_a
JOIN sku_freq fb ON fb.sku_code = p.sku_b
LEFT JOIN skus sa ON sa.dataset_id = '{ds}' AND sa.sku_code = p.sku_a
LEFT JOIN skus sb ON sb.dataset_id = '{ds}' AND sb.sku_code = p.sku_b
ORDER BY he_so_lift DESC, so_don_mua_chung DESC
LIMIT 15;""",
        },
        {
            "id": "rolling_7d_moving_avg",
            "title": "10. Đường Trung Bình Trượt 7 Ngày & Phát Hiện Ngày Hoàn Đơn Đột Biến",
            "skill_tags": ["ROWS 6 PRECEDING", "Moving Average", "Anomaly SQL"],
            "business_question": "Ngày nào có tỷ lệ hoàn đơn vượt xa đường trung bình trượt 7 ngày liền trước?",
            "sql": f"""-- Dùng Window Frame ROWS BETWEEN 6 PRECEDING AND CURRENT ROW làm mượt nhiễu ngày
WITH daily_stats AS (
    SELECT
        order_date,
        COUNT(*) AS tong_don_giao,
        SUM(CASE WHEN status = 'RETURNED' THEN 1 ELSE 0 END) AS don_hoan,
        ROUND(SUM(CASE WHEN status = 'RETURNED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS ty_le_hoan_ngay_pct
    FROM orders
    WHERE dataset_id = '{ds}' AND status IN ('COMPLETED', 'RETURNED')
    GROUP BY order_date
),
rolling AS (
    SELECT
        *,
        ROUND(
            AVG(ty_le_hoan_ngay_pct) OVER (
                ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ), 2
        ) AS ma7_ty_le_hoan_pct
    FROM daily_stats
)
SELECT
    order_date,
    tong_don_giao,
    don_hoan,
    ty_le_hoan_ngay_pct,
    ma7_ty_le_hoan_pct,
    ROUND(ty_le_hoan_ngay_pct - ma7_ty_le_hoan_pct, 2) AS chenh_lech_so_voi_ma7
FROM rolling
WHERE tong_don_giao >= 8
ORDER BY chenh_lech_so_voi_ma7 DESC
LIMIT 15;""",
        },
    ]
