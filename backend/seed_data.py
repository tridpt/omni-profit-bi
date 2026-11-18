"""
Realistic Vietnamese Omni-Channel Retail & E-Commerce Seed Data Generator.
Generates 3 complete 6-month multi-table analytical datasets (2026-05-01 -> 2026-10-31)
with authentic unit economics, Mega-Sale spikes, SKU margin traps, RFM customer lifecycles,
and ABC-XYZ inventory imbalances.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
import numpy as np

from .database import get_connection, init_db

VN_LAST_NAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
VN_MID_NAMES = ["Minh", "Thị", "Hoàng", "Ngọc", "Thanh", "Quốc", "Gia", "Phương", "Anh", "Đức", " Bảo", "Khánh"]
VN_FIRST_NAMES = ["Anh", "Linh", "Hùng", "Trang", "Tuấn", "Hương", "Nam", "Thảo", "Khôi", "Vy", "Dũng", "Mai", "Quân", "Nhi", "Phúc", "Hà"]
VN_CITIES = [
    ("TP. Hồ Chí Minh", 0.36),
    ("Hà Nội", 0.27),
    ("Đà Nẵng", 0.08),
    ("Bình Dương", 0.06),
    ("Hải Phòng", 0.05),
    ("Cần Thơ", 0.05),
    ("Đồng Nai", 0.05),
    ("Khánh Hòa", 0.04),
    ("Nghệ An", 0.04),
]

DOUBLE_DAYS = {(5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (5, 15), (6, 15), (7, 15), (8, 15), (9, 15), (10, 15), (10, 20)}


SCENARIOS: list[dict[str, Any]] = [
    {
        "dataset_id": "vn_fashion_omni",
        "name": "LocalWear Studio — Thời Trang Đa Kênh (Shopee • TikTok • Web • POS)",
        "industry": "Fashion & Apparel",
        "description": (
            "Thương hiệu thời trang ứng dụng 6 tháng (05/2026–10/2026): Doanh số bùng nổ mùa Mega Sale nhưng vướng bẫy "
            "'Áo thun mồi lỗ ròng', phí Affiliate TikTok chồng chéo, hoàn hàng lệch size 17.5% và nguy cơ đứt hàng Sơ mi chủ lực."
        ),
        "seed": 202601,
        "num_customers": 1150,
        "base_daily_orders": 21,
        "channels": [
            # name, weight, plat_fee_pct, pay_fee_pct, aff_prob, aff_pct, return_rate, cancel_rate, seller_ship, cac
            ("Shopee Mall", 0.40, 0.082, 0.040, 0.28, 0.075, 0.105, 0.055, 8000, 48000),
            ("TikTok Shop", 0.34, 0.065, 0.040, 0.68, 0.115, 0.172, 0.065, 9500, 56000),
            ("Website D2C", 0.14, 0.000, 0.022, 0.10, 0.050, 0.055, 0.030, 12000, 72000),
            ("Cửa hàng POS", 0.12, 0.000, 0.008, 0.00, 0.000, 0.015, 0.005, 0, 25000),
        ],
        "skus": [
            # code, name, cat, list_price, cogs, pack, stock, lead_days, moq, elast, weight, promo_bias, ad_daily_base, extra_ret
            ("FASH-TEE-01", "Áo Thun Cotton 250gsm Basic (Mồi)", "Áo Thun", 159000, 82000, 6500, 420, 7, 100, -1.85, 0.20, 0.22, 460000, 0.01),
            ("FASH-OXF-02", "Sơ Mi Oxford Chống Nhăn Premium", "Áo Sơ Mi", 389000, 142000, 8500, 38, 10, 80, -1.15, 0.16, 0.09, 260000, -0.02),
            ("FASH-TRS-03", "Quần Âu Sidetab Slimfit Co Giãn", "Quần Dài", 449000, 168000, 9000, 165, 10, 60, -1.20, 0.13, 0.10, 230000, 0.03),
            ("FASH-BLZ-04", "Áo Blazer Hàn Quốc 2 Lớp (Dễ lệch size)", "Áo Khoác", 690000, 345000, 15000, 92, 14, 40, -1.45, 0.08, 0.16, 390000, 0.09),
            ("FASH-POL-05", "Áo Polo Pique Mắt Chim Thoáng Khí", "Áo Polo", 279000, 108000, 7000, 210, 7, 80, -1.35, 0.12, 0.11, 180000, 0.00),
            ("FASH-JNS-06", "Quần Jeans Selvedge Ống Đứng", "Quần Dài", 520000, 210000, 9500, 44, 12, 50, -1.25, 0.08, 0.08, 150000, 0.02),
            ("FASH-SHT-07", "Quần Short Kaki Linen Mùa Hè", "Quần Short", 249000, 95000, 6000, 185, 7, 60, -1.40, 0.07, 0.12, 95000, -0.01),
            ("FASH-CRD-08", "Áo Cardigan Dệt Kim Mỏng", "Áo Khoác", 359000, 148000, 8000, 130, 10, 50, -1.30, 0.05, 0.10, 85000, 0.01),
            ("FASH-BLT-09", "Thắt Lưng Da Bò Khóa Tự Động", "Phụ Kiện", 299000, 88000, 7500, 190, 6, 50, -0.95, 0.05, 0.05, 55000, -0.04),
            ("FASH-SCK-10", "Combo 5 Đôi Tất Khử Mùi Bamboo", "Phụ Kiện", 119000, 36000, 4000, 510, 5, 120, -1.10, 0.04, 0.06, 30000, -0.05),
            ("FASH-JKT-11", "Áo Khoác Da Lộn Cổ Bẻ (Tồn đọng vốn)", "Áo Khoác", 890000, 460000, 18000, 265, 15, 30, -1.60, 0.012, 0.14, 90000, 0.05),
            ("FASH-BAG-12", "Túi Tote Canvas Phối Da Đựng Laptop", "Phụ Kiện", 329000, 122000, 8500, 28, 9, 40, -1.20, 0.028, 0.08, 65000, -0.02),
        ],
    },
    {
        "dataset_id": "vn_skincare_d2c",
        "name": "DermaLab VN — Dược Mỹ Phẩm D2C (Shopee • TikTok Live • Zalo CRM • Showroom)",
        "industry": "Beauty & Skincare",
        "description": (
            "Thương hiệu dược mỹ phẩm nội địa: Chi phí thu hút khách mới (CAC) qua KOC/Livestream cao, lợi nhuận thực quyết định bởi "
            "tỷ lệ quay lại mua chu kỳ 35–50 ngày trên Zalo MiniApp & bộ Kit phục hồi biên lãi cao."
        ),
        "seed": 202602,
        "num_customers": 980,
        "base_daily_orders": 19,
        "channels": [
            ("Shopee Mall", 0.38, 0.085, 0.040, 0.35, 0.085, 0.065, 0.045, 7000, 68000),
            ("TikTok Live", 0.33, 0.065, 0.040, 0.78, 0.135, 0.115, 0.060, 9000, 82000),
            ("Zalo MiniApp", 0.19, 0.000, 0.018, 0.00, 0.000, 0.022, 0.015, 6000, 32000),
            ("Showroom Q1", 0.10, 0.000, 0.010, 0.00, 0.000, 0.008, 0.005, 0, 45000),
        ],
        "skus": [
            ("SKIN-CLN-01", "Sữa Rửa Mặt Amino pH 5.5 150ml (Mồi)", "Làm Sạch", 185000, 88000, 7500, 390, 7, 120, -1.75, 0.21, 0.21, 430000, 0.01),
            ("SKIN-SRM-02", "Serum Vitamin B5 + HA Cấp Ẩm Sâu 30ml", "Đặc Trị", 420000, 118000, 11000, 42, 12, 100, -1.05, 0.19, 0.08, 310000, -0.01),
            ("SKIN-SUN-03", "Kem Chống Nắng Phổ Rộng SPF50+ Kiềm Dầu", "Chống Nắng", 365000, 112000, 9500, 175, 10, 100, -1.15, 0.17, 0.10, 270000, 0.00),
            ("SKIN-RET-04", "Tinh Chất Retinol Bọc Vi Nang 0.5%", "Đặc Trị", 590000, 175000, 13000, 98, 14, 60, -1.20, 0.10, 0.09, 210000, 0.04),
            ("SKIN-KIT-05", "Bộ Đôi Phục Hồi Màng Bảo Vệ Da Fullsize", "Combo VIP", 790000, 228000, 18000, 64, 12, 50, -1.10, 0.09, 0.07, 190000, -0.02),
            ("SKIN-TON-06", "Toner Pad Rau Má Làm Dịu Da (70 miếng)", "Làm Sạch", 295000, 105000, 8500, 215, 8, 80, -1.35, 0.10, 0.12, 140000, 0.00),
            ("SKIN-MSK-07", "Hộp 5 Mặt Nạ Sinh Học Cấp Nước Tức Thì", "Mặt Nạ", 210000, 72000, 6500, 310, 6, 100, -1.30, 0.08, 0.10, 95000, -0.02),
            ("SKIN-EYE-08", "Máy Điện Di Mắt Mini Kèm Kem Peptide (Đọng kho)", "Thiết Bị", 950000, 520000, 22000, 195, 18, 30, -1.65, 0.015, 0.17, 135000, 0.06),
            ("SKIN-LIP-09", "Son Dưỡng Phục Hồi Môi Ceramide", "Chăm Sóc Môi", 145000, 42000, 5000, 32, 7, 100, -1.10, 0.045, 0.06, 45000, -0.03),
        ],
    },
    {
        "dataset_id": "vn_coffee_chain",
        "name": "Cao Nguyên Roastery — Chuỗi Cà Phê Đặc Sản & Hạt Rang Đa Kênh",
        "industry": "F&B & Specialty Coffee",
        "description": (
            "Chuỗi cà phê & xưởng rang bán lẻ: Đối mặt bài toán chiết khấu App giao đồ ăn 25% ăn mòn biên lãi thức uống lẻ, "
            "cần dịch chuyển khách sang Combo Hạt Rang & tối ưu tồn kho Arabica chủ lực."
        ),
        "seed": 202603,
        "num_customers": 920,
        "base_daily_orders": 22,
        "channels": [
            ("Quầy POS Flagship", 0.34, 0.000, 0.008, 0.00, 0.000, 0.005, 0.005, 0, 18000),
            ("GrabFood / ShopeeFood", 0.32, 0.245, 0.020, 0.00, 0.000, 0.035, 0.040, 5000, 29000),
            ("Shopee Hạt Rang", 0.22, 0.078, 0.040, 0.25, 0.070, 0.048, 0.035, 7000, 42000),
            ("Website / B2B Quán", 0.12, 0.000, 0.015, 0.00, 0.000, 0.010, 0.010, 10000, 55000),
        ],
        "skus": [
            ("COF-DRK-01", "Combo 2 Ly Phin Sữa Đá Đậm Vị (Mồi App)", "Thức Uống", 89000, 39000, 7500, 600, 3, 200, -1.70, 0.22, 0.18, 280000, 0.01),
            ("COF-ARA-02", "Hạt Arabica Cầu Đất Honey 500g", "Hạt Rang", 295000, 118000, 9000, 34, 9, 80, -1.05, 0.19, 0.07, 195000, -0.01),
            ("COF-CLD-03", "Chai Cold Brew Ủ Lạnh Cam Vàng 500ml", "Đóng Chai", 135000, 46000, 8000, 140, 4, 100, -1.20, 0.16, 0.09, 140000, 0.00),
            ("COF-ROB-04", "Hạt Fine Robusta Gia Lai Rang Vừa 1kg", "Hạt Rang", 360000, 145000, 11000, 125, 8, 60, -1.10, 0.14, 0.08, 130000, -0.01),
            ("COF-DRP-05", "Hộp 10 Túi Cà Phê Phin Giấy Drip Bag", "Tiện Lợi", 189000, 68000, 8500, 220, 7, 80, -1.25, 0.12, 0.10, 125000, 0.00),
            ("COF-MAT-06", "Bột Matcha Uji Nhật Bản Pha Latte 100g", "Nguyên Liệu", 320000, 142000, 7500, 38, 12, 50, -1.15, 0.09, 0.07, 110000, 0.00),
            ("COF-TLS-07", "Bộ Ấm Rót Cổ Ngỗng & Phễu Thủy Tinh V60 (Tồn lâu)", "Dụng Cụ", 780000, 430000, 20000, 165, 16, 25, -1.60, 0.02, 0.15, 85000, 0.04),
            ("COF-SYR-08", "Syrup Đường Đen & Hạt Phỉ Rang 750ml", "Nguyên Liệu", 215000, 89000, 7000, 155, 7, 50, -1.30, 0.06, 0.08, 60000, 0.00),
        ],
    },
]


def _generate_scenario_data(cfg: dict[str, Any]) -> None:
    rng = np.random.default_rng(cfg["seed"])
    ds_id = cfg["dataset_id"]
    start_date = date(2026, 5, 1)
    end_date = date(2026, 10, 31)
    total_days = (end_date - start_date).days + 1

    channels = cfg["channels"]
    chan_names = [c[0] for c in channels]
    chan_weights = np.array([c[1] for c in channels], dtype=float)
    chan_weights /= chan_weights.sum()
    chan_map = {c[0]: c for c in channels}

    skus = cfg["skus"]
    sku_codes = [s[0] for s in skus]
    sku_weights = np.array([s[10] for s in skus], dtype=float)
    sku_weights /= sku_weights.sum()
    sku_map = {s[0]: s for s in skus}

    cities = [c[0] for c in VN_CITIES]
    city_weights = np.array([c[1] for c in VN_CITIES], dtype=float)
    city_weights /= city_weights.sum()

    # 1. Generate Customers with realistic lifecycle cohorts & loyalty tiers
    num_customers = cfg["num_customers"]
    customer_rows = []
    cust_profiles: list[dict[str, Any]] = []

    for idx in range(1, num_customers + 1):
        cid = f"CUS-{idx:04d}"
        full_name = f"{rng.choice(VN_LAST_NAMES)} {rng.choice(VN_MID_NAMES).strip()} {rng.choice(VN_FIRST_NAMES)}"
        phone = f"09{int(rng.integers(10, 99))}***{int(rng.integers(100, 999))}"
        city = str(rng.choice(cities, p=city_weights))
        acq_chan = str(rng.choice(chan_names, p=chan_weights))
        base_cac = chan_map[acq_chan][9]
        cac = round(float(base_cac * rng.uniform(0.75, 1.35)), -2)

        # Spread customer acquisition across the 6 months (heavier earlier so cohorts mature)
        join_offset = int(np.clip(rng.beta(1.5, 2.2) * (total_days - 5), 0, total_days - 2))
        join_dt = start_date + timedelta(days=join_offset)

        # Behavioral archetype for realistic RFM & At-Risk patterns:
        # 14% VIP Champions, 22% Steady Loyal, 16% At-Risk Former VIP (stopped ~55-95 days ago!), 28% One-Timers, 20% Promo/Occasional
        archetype_roll = float(rng.random())
        if archetype_roll < 0.14:
            archetype = "CHAMPION"
            propensity = float(rng.uniform(3.2, 5.5))
            churn_after_day = 999
        elif archetype_roll < 0.36:
            archetype = "LOYAL"
            propensity = float(rng.uniform(1.8, 3.0))
            churn_after_day = 999
        elif archetype_roll < 0.52 and join_offset < 95:
            archetype = "AT_RISK_VIP"
            propensity = float(rng.uniform(2.6, 4.2))
            # Active early, then stopped before mid-August / early September!
            churn_after_day = int(rng.integers(max(join_offset + 25, 65), 132))
        elif archetype_roll < 0.80:
            archetype = "ONE_TIME"
            propensity = 0.25
            churn_after_day = join_offset + 3
        else:
            archetype = "OCCASIONAL"
            propensity = float(rng.uniform(0.8, 1.6))
            churn_after_day = 999

        cust_profiles.append(
            {
                "customer_id": cid,
                "join_offset": join_offset,
                "join_date": join_dt,
                "pref_channel": acq_chan,
                "archetype": archetype,
                "propensity": propensity,
                "churn_after_day": churn_after_day,
                "first_order_recorded": None,
                "full_name": full_name,
                "phone": phone,
                "city": city,
                "cac": cac,
            }
        )

    # 2. Simulate day-by-day orders & marketing spend
    order_rows = []
    item_rows = []
    mkt_rows = []
    order_seq = 10001

    # Guarantee first order on join_offset for most customers + repeat orders
    by_join_day: dict[int, list[dict[str, Any]]] = {}
    for cp in cust_profiles:
        by_join_day.setdefault(cp["join_offset"], []).append(cp)

    for day_idx in range(total_days):
        curr_dt = start_date + timedelta(days=day_idx)
        dt_str = curr_dt.isoformat()
        month_str = curr_dt.strftime("%Y-%m")
        is_double_day = (curr_dt.month, curr_dt.day) in DOUBLE_DAYS
        is_near_mega = (not is_double_day) and any(
            abs((curr_dt - date(2026, m_d, m_d)).days) in (1, 2) for m_d in (5, 6, 7, 8, 9, 10)
        )
        is_weekend = curr_dt.weekday() >= 5
        # Gradual growth trend across months + October Mega Push + Pre/Post-Promo Dip
        month_growth = 1.0 + 0.045 * (curr_dt.month - 5)
        oct_push = 1.16 if curr_dt.month == 10 else 1.0
        dip_mult = 0.76 if is_near_mega else 1.0
        promo_mult = (2.55 if is_double_day else (1.18 if is_weekend else 1.0)) * month_growth * oct_push * dip_mult

        # Daily marketing spend per SKU
        for s in skus:
            s_code = s[0]
            base_ad = s[12]
            ad_mult = (2.6 if is_double_day else (1.2 if is_weekend else 0.92)) * month_growth
            if curr_dt.month == 10 and s_code == skus[0][0]:
                # October aggressive ad push on hero/bait SKU
                ad_mult *= 1.42
            spend = round(float(base_ad * ad_mult * rng.uniform(0.82, 1.20)), -2)
            # Assign spend to top paid channel (Shopee or TikTok)
            ad_chan = chan_names[1] if rng.random() < 0.54 else chan_names[0]
            cpc = float(rng.uniform(2400, 4800))
            clicks = max(12, int(spend / cpc))
            impressions = int(clicks * rng.uniform(28, 58))
            mkt_rows.append((ds_id, dt_str, month_str, ad_chan, s_code, spend, impressions, clicks))

        # Determine customers ordering today: new joiners + active repeaters
        todays_buyers: list[tuple[dict[str, Any], bool]] = []
        for new_cp in by_join_day.get(day_idx, []):
            todays_buyers.append((new_cp, True))

        eligible_repeaters = [
            cp
            for cp in cust_profiles
            if cp["join_offset"] < day_idx <= cp["churn_after_day"] and cp["archetype"] != "ONE_TIME"
        ]
        target_repeat_orders = int(round(cfg["base_daily_orders"] * promo_mult * 0.72))
        if eligible_repeaters and target_repeat_orders > 0:
            weights = np.array([cp["propensity"] for cp in eligible_repeaters], dtype=float)
            weights /= weights.sum()
            chosen_count = min(len(eligible_repeaters), max(2, int(rng.poisson(target_repeat_orders))))
            chosen_idxs = rng.choice(len(eligible_repeaters), size=chosen_count, replace=False, p=weights)
            for c_idx in chosen_idxs:
                todays_buyers.append((eligible_repeaters[int(c_idx)], False))

        for cp, is_first in todays_buyers:
            order_id = f"ORD-{curr_dt.strftime('%y%m')}-{order_seq:05d}"
            order_seq += 1

            if cp["first_order_recorded"] is None:
                cp["first_order_recorded"] = dt_str

            # Repeat loyalists in Skincare/Coffee shift slightly toward CRM/Web/POS
            if not is_first and rng.random() < 0.62:
                chan_name = cp["pref_channel"]
            else:
                # October pushes more TikTok volume
                adj_weights = chan_weights.copy()
                if curr_dt.month == 10 and len(adj_weights) > 1:
                    adj_weights[1] *= 1.30
                    adj_weights /= adj_weights.sum()
                chan_name = str(rng.choice(chan_names, p=adj_weights))

            c_info = chan_map[chan_name]
            _, _, plat_pct, pay_pct, aff_prob, aff_pct, base_ret_rate, cancel_rate, base_ship_seller, _ = c_info

            # Pick 1 to 3 distinct SKUs with realistic complementary basket affinity (Lift > 1.5x)
            num_items = int(rng.choice([1, 2, 3], p=[0.56, 0.33, 0.11]))
            first_idx = int(rng.choice(len(skus), p=sku_weights))
            picked_list = [first_idx]
            if num_items > 1 and len(skus) > 2:
                cond_w = sku_weights.copy()
                cond_w[first_idx] = 0.0
                # Symmetric cross-sell affinities (Bait SKU <-> High-Margin Jeans/Polo; Oxford <-> Trousers/Belt)
                affinity_map = {
                    0: [4, 5],
                    1: [2, 8 if len(skus) > 8 else 3],
                    2: [1, 8 if len(skus) > 8 else 3],
                    3: [1, 2],
                    4: [0, 6 if len(skus) > 6 else 1],
                    5: [0, 8 if len(skus) > 8 else 2],
                }
                for partner in affinity_map.get(first_idx, []):
                    if partner < len(cond_w) and partner != first_idx:
                        cond_w[partner] *= 6.5
                cond_w /= cond_w.sum()
                extra_picks = rng.choice(len(skus), size=min(num_items - 1, len(skus) - 1), replace=False, p=cond_w)
                picked_list.extend(int(x) for x in extra_picks)
            picked_skus = np.array(picked_list, dtype=int)

            # Determine order status (weighted by SKU return risk + Oct 14-16 courier/batch defect anomaly)
            avg_extra_ret = float(np.mean([skus[int(si)][13] for si in picked_skus]))
            anomaly_bump = 0.19 if curr_dt in (date(2026, 10, 14), date(2026, 10, 16)) else 0.0
            eff_ret_rate = np.clip(base_ret_rate + avg_extra_ret + anomaly_bump + (0.025 if is_double_day else 0.0), 0.005, 0.48)
            status_roll = float(rng.random())
            if status_roll < cancel_rate:
                status = "CANCELLED"
            elif status_roll < cancel_rate + eff_ret_rate:
                status = "RETURNED"
            else:
                status = "COMPLETED"

            has_affiliate = rng.random() < (aff_prob * (1.22 if is_double_day or curr_dt.month == 10 else 1.0))
            eff_aff_pct = aff_pct if has_affiliate else 0.0

            ord_gross = 0.0
            ord_seller_disc = 0.0
            ord_plat_sub = 0.0
            ord_plat_fee = 0.0
            ord_pay_fee = 0.0
            ord_aff_fee = 0.0
            ord_ship_seller = 0.0
            ord_ret_fee = 0.0

            temp_items = []
            for si in picked_skus:
                s_row = skus[int(si)]
                s_code, _, _, list_price, unit_cogs, pack_cost, _, _, _, _, _, promo_bias, _, _ = s_row
                qty = int(rng.choice([1, 2, 3], p=[0.78, 0.17, 0.05]))
                line_gross = float(list_price * qty)

                # Seller discount rate increases on Double Days & October Mega Sale & Bait SKUs
                disc_pct = promo_bias * float(rng.uniform(0.55, 1.15))
                if is_double_day:
                    disc_pct += 0.065
                if curr_dt.month == 10:
                    disc_pct += 0.025
                disc_pct = float(np.clip(disc_pct, 0.0, 0.35))
                seller_disc = round(line_gross * disc_pct, -2)
                plat_sub = round(line_gross * (0.04 if is_double_day and plat_pct > 0 else 0.0), -2)
                temp_items.append((s_code, qty, list_price, unit_cogs, pack_cost, line_gross, seller_disc, plat_sub))
                ord_gross += line_gross
                ord_seller_disc += seller_disc
                ord_plat_sub += plat_sub

            ship_seller_total = float(base_ship_seller * (1.25 if is_double_day and base_ship_seller > 0 else 1.0))

            for s_code, qty, list_price, unit_cogs, pack_cost, line_gross, seller_disc, _ in temp_items:
                share = line_gross / ord_gross if ord_gross > 0 else 0.0
                if status == "COMPLETED":
                    net_rev = line_gross - seller_disc
                    cogs_total = float(unit_cogs * qty)
                    pack_total = float(pack_cost * qty)
                    p_fee = round(net_rev * plat_pct, 0)
                    pay_fee = round((net_rev + ord_plat_sub * share) * pay_pct, 0)
                    a_fee = round(net_rev * eff_aff_pct, 0)
                    s_ship = round(ship_seller_total * share, 0)
                    ret_loss = 0.0
                elif status == "RETURNED":
                    # Returned / BOM order: 0 revenue realized, seller loses packaging + 2-way return logistics + 12% restocking damage
                    net_rev = 0.0
                    cogs_total = 0.0
                    pack_total = 0.0
                    p_fee = 0.0
                    pay_fee = 0.0
                    a_fee = 0.0
                    s_ship = 0.0
                    two_way_ship = (26000.0 if base_ship_seller > 0 else 8000.0) * share
                    damage_writeoff = float(unit_cogs * qty) * 0.12
                    ret_loss = round(float(pack_cost * qty) + two_way_ship + damage_writeoff, 0)
                else:  # CANCELLED before fulfillment
                    net_rev = 0.0
                    cogs_total = 0.0
                    pack_total = 0.0
                    p_fee = 0.0
                    pay_fee = 0.0
                    a_fee = 0.0
                    s_ship = 0.0
                    ret_loss = 0.0

                ord_plat_fee += p_fee
                ord_pay_fee += pay_fee
                ord_aff_fee += a_fee
                ord_ship_seller += s_ship
                ord_ret_fee += ret_loss

                item_rows.append(
                    (
                        ds_id,
                        order_id,
                        s_code,
                        qty,
                        list_price,
                        line_gross,
                        seller_disc,
                        net_rev,
                        cogs_total,
                        pack_total,
                        p_fee,
                        pay_fee,
                        a_fee,
                        s_ship,
                        ret_loss,
                    )
                )

            order_rows.append(
                (
                    ds_id,
                    order_id,
                    dt_str,
                    month_str,
                    chan_name,
                    cp["customer_id"],
                    status,
                    ord_gross,
                    ord_seller_disc,
                    ord_plat_sub,
                    ord_ship_seller,
                    ord_ret_fee,
                    ord_plat_fee,
                    ord_pay_fee,
                    ord_aff_fee,
                )
            )

    for cp in cust_profiles:
        first_dt = cp["first_order_recorded"] or cp["join_date"].isoformat()
        customer_rows.append(
            (
                ds_id,
                cp["customer_id"],
                cp["full_name"],
                cp["phone"],
                cp["city"],
                cp["pref_channel"],
                cp["cac"],
                first_dt,
            )
        )

    sku_db_rows = [
        (ds_id, s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9])
        for s in skus
    ]

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(readonly=False) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO datasets (dataset_id, name, industry, description, currency, created_at, is_builtin)
            VALUES (?, ?, ?, ?, 'VND', ?, 1)
            """,
            (ds_id, cfg["name"], cfg["industry"], cfg["description"], now_iso),
        )
        conn.executemany(
            """
            INSERT INTO skus (
                dataset_id, sku_code, product_name, category, list_price, unit_cogs,
                packaging_cost, current_stock, lead_time_days, min_order_qty, price_elasticity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sku_db_rows,
        )
        conn.executemany(
            """
            INSERT INTO customers (
                dataset_id, customer_id, customer_name, phone_masked, city,
                acquisition_channel, acquisition_cost, first_order_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            customer_rows,
        )
        conn.executemany(
            """
            INSERT INTO orders (
                dataset_id, order_id, order_date, order_month, channel, customer_id, status,
                gross_amount, seller_voucher, platform_subsidy, shipping_fee_seller,
                return_logistics_fee, platform_fee, payment_fee, affiliate_fee
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order_rows,
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
        conn.executemany(
            """
            INSERT INTO marketing_daily (
                dataset_id, spend_date, spend_month, channel, sku_code, ad_spend, impressions, clicks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            mkt_rows,
        )
        conn.commit()


def ensure_seed_data(force_reseed: bool = False) -> None:
    """Initialize DB and generate any missing built-in scenarios."""
    init_db()
    with get_connection(readonly=False) as conn:
        existing = {
            row["dataset_id"]
            for row in conn.execute("SELECT dataset_id FROM datasets WHERE is_builtin = 1").fetchall()
        }

    for cfg in SCENARIOS:
        ds_id = cfg["dataset_id"]
        if force_reseed or ds_id not in existing:
            if ds_id in existing:
                from .database import delete_dataset
                delete_dataset(ds_id)
            _generate_scenario_data(cfg)
