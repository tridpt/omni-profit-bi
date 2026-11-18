# 📈 ProfitPulse BI — Hệ Thống Phân Tích Lãi Ròng Thực, Khách Hàng RFM & Tồn Kho Đa Kênh (`Port 8045`)

**End-to-End Retail & E-Commerce Decision Intelligence Platform • SQLite Analytical Warehouse (CTE & Window Functions) • Python (FastAPI, Pandas, NumPy, SciPy, OpenPyXL) • Interactive BI & What-If Simulator**

---

## 🎯 Bài Toán Thực Tế Giải Quyết

Hầu hết các chủ shop Shopee / TikTok Shop, chuỗi F&B, D2C và doanh nghiệp bán lẻ tại Việt Nam chỉ nhìn vào **GMV (Tổng doanh số đặt hàng)** mà không thấy được **Lãi ròng thực tế bỏ túi**, dẫn tới 3 "cái bẫy" kinh điển:
1. **Bẫy Doanh Thu Ảo (Profit Bleeders):** Sản phẩm mồi bán hàng nghìn đơn nhưng âm tiền mặt sau khi trừ Giá vốn, Bao bì, Voucher trợ giá, Phí sàn tăng, Hoa hồng Affiliate KOL, Thiệt hại bom/hoàn hàng 2 chiều và Chi phí Ads.
2. **Đốt Tiền Chăm Sóc Khách Hàng Mù Quáng:** Rải voucher đại trà thay vì định lượng **RFM + Cohort Retention** và tối ưu phân bổ ngân sách có giới hạn theo kỳ vọng sinh lời tăng thêm (**Incremental ROI**).
3. **Vừa Đứt Hàng Chủ Lực, Vừa Chôn Vốn Tồn Chết:** Nhập hàng theo cảm tính thay vì ma trận **`ABC-XYZ`**, **Tồn kho an toàn (`Safety Stock`)** và **Điểm đặt hàng lại (`ROP`)**.

---

## ✨ 5 Phân Hệ Phân Tích Cốt Lõi

1. **💰 Giải Phẫu Lãi Ròng Thực & Cầu Nối Biến Động (`Unit Economics Waterfall & MoM Variance Bridge`)**
   - Bóc tách từng đồng từ `GMV Đơn Thành Công` ➔ `Voucher Shop` ➔ `Doanh Thu Thuần` ➔ `Giá Vốn + Đóng Gói` ➔ `Phí Sàn & Thanh Toán` ➔ `Affiliate` ➔ `Đơn Hoàn` ➔ `Ads` = **`Lãi Ròng Thực`** & chỉ số **`POAS` (Profit on Ad Spend)**.
   - **Tự động giải phẫu biến động tháng gần nhất (Price-Volume-Mix-Fee Bridge):** Trả lời ngay câu hỏi của Giám đốc *"Tại sao doanh thu tháng 10 tăng +14% nhưng lãi ròng lại sụt giảm?"*.
   - Bảng xếp hạng **Cash Cows vs Profit Bleeders** từng mã hàng SKU kèm nút nhảy 1-chạm sang Phòng Giả Lập.

2. **👥 Phân Khúc Khách Hàng RFM (`SQL NTILE(5)`), Cohort Retention & Tối Ưu Ngân Sách Cứu Khách**
   - Chấm điểm RFM trực tiếp bằng SQL Window Functions, đo tỷ số bền vững **`LTV : CAC`**.
   - Ma trận nhiệt **Cohort Retention (`M0 ➔ M5`)** theo tháng mua đầu tiên.
   - **Knapsack Retention Budget Optimizer:** Cho trước ngân sách giới hạn (VD: `15.000.000 đ`), thuật toán chọn ra danh sách khách hàng tối ưu hóa **Lãi ròng tăng thêm kỳ vọng** và xuất thẳng file `.CSV` chạy Zalo ZNS / SMS.

3. **📦 Quản Trị Tồn Kho Thông Minh `ABC-XYZ` & Cảnh Báo Đứt Hàng**
   - Phân hạng `ABC` theo đóng góp lợi nhuận Pareto tích lũy (`80% - 15% - 5%`) kết hợp `XYZ` theo hệ số biến thiên cầu hàng tuần (`CV = σ / μ`).
   - Tự động tính `Safety Stock = Z × σ_daily × √LeadTime`, `Reorder Point (ROP)`, `Days of Inventory (DOI)` và tổng vốn bị chôn ở hàng tồn đọng.

4. **🎛️ Phòng Giả Lập Quyết Định Giá, Phí Sàn & Điểm Hòa Vốn (`Elastic What-If Simulator`)**
   - Mô phỏng độ co giãn của cầu theo giá (`Price Elasticity ε`) khi tăng/giảm giá niêm yết, thay đổi Voucher, sàn tăng phí hoặc thay đổi ngân sách Ads.
   - Vẽ **Đường cong nhạy cảm giá (`-20% ➔ +25%`)** chỉ ra **Đỉnh giá tối ưu hóa lợi nhuận** và cảnh báo đỏ khi biên đóng góp đơn vị âm (`Unit Contribution ≤ 0`).

5. **🔮 Dự Báo Chuỗi Thời Gian 30 Ngày, Kiểm Định `SciPy p-value`, Cảnh Báo `Z-Score` & Ghép Combo `Lift` (`v2.0`)**
   - **Holt Damped Seasonal Forecast (30 Ngày):** Khử nhiễu chu kỳ 7 ngày + hệ số bùng nổ ngày đôi, kiểm định chéo Out-of-Sample Backtest (WAPE/Accuracy) và vẽ biểu đồ **Fan Chart dải tin cậy `P10 • P50 • P90`** kèm dự phóng Vốn lưu động cần chuẩn bị.
   - **Kiểm định giả thuyết thống kê (`scipy.stats`):** `Welch's t-test` đánh giá hiệu quả ngày Mega Sale & hiệu ứng khách găm đơn chờ Sale (*Pre/Post-Promo Cannibalization Dip*), cùng kiểm định `Chi-Square (χ²)` độc lập tỷ lệ hoàn đơn giữa các kênh.
   - **Khai phá giỏ hàng (`Market Basket Support, Confidence, Lift`):** Tự động thiết kế **Combo 1 kiện hàng** ghép các mã lỗ ngầm với mã lãi cao có `Lift > 1.2x` để đảo chiều từ lỗ sang lãi ròng > 20%.
   - **Rada kiểm soát quá trình thống kê (`SPC Z-Score ≥ 2.3σ`):** Tự động bắt các ngày hoàn đơn tăng vọt bất thường hoặc rò rỉ ngân sách Ads.

6. **🗄️ Phòng Lab SQL Thực Chiến (10 Mẫu) & Bộ Lọc Dữ Liệu Bẩn Thực Tế (`.xlsx` / `.csv`)**
   - **10 mẫu câu truy vấn SQL chuẩn phỏng vấn Senior Data Analyst** (`Multi-CTE`, `SUM() OVER` Pareto, `NTILE(5) OVER`, `LAG() OVER`, `Index Self-Join Lift`, `Rolling 7-Day Moving Average`...) chạy trực tiếp trên kho SQLite ở chế độ Read-Only Sandbox.
   - **Nạp file Excel/CSV thực tế:** Tự động nhận diện cột tiếng Việt/Anh và làm sạch chuỗi tiền tệ bẩn (`"389.000 đ"`, `"389,000"`), chuẩn hóa ngày `dd/mm/yyyy`, khử dòng trùng và xuất **Báo cáo Điều hành CEO 6 Sheet (`.xlsx`)**.

---

## 🚀 Cách Chạy Ứng Dụng

```powershell
cd d:\AI_App\omni-profit-bi
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8045
```
Hoặc nháy đúp vào tệp `start_profit_bi.bat`, sau đó mở trình duyệt tại **`http://127.0.0.1:8045`**.

Chạy bộ kiểm thử tự động (`pytest`):
```powershell
cd d:\AI_App\omni-profit-bi
python -m pytest -v
```

---

## 🎓 Gợi Ý Đưa Dự Án Vào CV Data Analyst

> **Omni-Channel Retail Profit, Customer Lifecycle & Inventory Intelligence (`Python, SQL, FastAPI, Pandas`)**
> - Thiết kế kho dữ liệu phân tích đa kênh (4.600+ đơn hàng/kịch bản) bóc tách **SKU-level Unit Economics** & **MoM Variance Bridge**, phát hiện nhóm sản phẩm mồi gây thất thoát biên lợi nhuận ròng do phí sàn, Affiliate và hoàn đơn.
> - Xây dựng mô hình phân khúc **RFM (`SQL NTILE Window Function`)**, **Cohort Retention Matrix** và thuật toán phân bổ ngân sách giữ chân khách hàng có ràng buộc ngân sách (**Knapsack ROI Optimizer**).
> - Triển khai hệ thống phân loại tồn kho **ABC-XYZ**, tính toán **Safety Stock / Reorder Point (ROP)** theo mức độ phục vụ thống kê (95% Service Level) và công cụ giả lập độ co giãn giá (**Price Elasticity What-If Simulator**).
