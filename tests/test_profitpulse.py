"""
Automated Test Suite for ProfitPulse BI:
Verifies Unit Economics P&L reconciliation, Variance Bridge math, SQL Sandbox security,
RFM/Cohort/Knapsack optimizer constraints, ABC-XYZ inventory math, What-If simulator,
and messy Vietnamese Excel (.xlsx) import/export roundtrip.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.seed_data import ensure_seed_data


@pytest.fixture(scope="module", autouse=True)
def setup_warehouse():
    ensure_seed_data(force_reseed=False)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_and_datasets(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    ds_res = client.get("/api/datasets").json()["datasets"]
    ids = [d["dataset_id"] for d in ds_res]
    assert "vn_fashion_omni" in ids
    assert "vn_skincare_d2c" in ids
    assert "vn_coffee_chain" in ids


def test_pnl_waterfall_and_variance_reconciliation(client: TestClient):
    data = client.get("/api/overview?dataset_id=vn_fashion_omni").json()
    k = data["kpis"]
    # Exact accounting identity check (within rounding of 5 VND)
    recomputed_net = (
        k["completed_gross"]
        - k["seller_discount"]
        - k["cogs_pack"]
        - k["platform_and_payment_fees"]
        - k["affiliate_fee"]
        - k["shipping_seller"]
        - k["return_loss"]
        - k["ad_spend"]
    )
    assert abs(recomputed_net - k["true_net_profit"]) <= 10

    # Variance bridge exact sum check
    vb = data["variance_bridge"]
    assert vb["available"] is True
    deltas_sum = sum(s["value"] for s in vb["steps"] if s["type"] == "delta")
    assert abs((vb["prev_profit"] + deltas_sum) - vb["curr_profit"]) <= 15

    # Profit bleeders detected
    bleeders = [s for s in data["sku_pnl"] if s["badge"] == "BLEEDER"]
    assert len(bleeders) >= 1


def test_rfm_cohort_and_knapsack_budget_cap(client: TestClient):
    budget = 10_000_000
    res = client.get(f"/api/rfm-cohort?dataset_id=vn_fashion_omni&budget_vnd={budget}").json()
    assert res["summary"]["active_customers"] > 500
    for c_row in res["cohort_matrix"]:
        assert c_row["retention"]["M0"] == 100.0

    opt = res["optimizer"]
    assert 0 < opt["budget_used"] <= budget
    assert opt["projected_incremental_net_profit"] > 0
    assert opt["customers_selected"] > 0


def test_inventory_abc_xyz_engine(client: TestClient):
    inv = client.get("/api/inventory?dataset_id=vn_fashion_omni").json()
    assert inv["summary"]["total_skus"] == 12
    assert len(inv["matrix"]) == 9
    for item in inv["items"]:
        assert item["abc"] in ("A", "B", "C")
        assert item["xyz"] in ("X", "Y", "Z")
        assert item["reorder_point"] >= item["safety_stock"]


def test_what_if_simulator_identity_and_trap(client: TestClient):
    # 0% changes must match baseline exactly
    r0 = client.post("/api/simulate", json={"dataset_id": "vn_fashion_omni"}).json()
    assert abs(r0["baseline"]["net_profit"] - r0["simulated"]["net_profit"]) <= 5

    # Extreme voucher + fee hike triggers negative unit contribution margin warning
    r_trap = client.post(
        "/api/simulate",
        json={
            "dataset_id": "vn_fashion_omni",
            "sku_code": "FASH-TEE-01",
            "voucher_change_pts": 20.0,
            "platform_fee_change_pts": 15.0,
        },
    ).json()
    assert r_trap["negative_unit_margin"] is True
    assert r_trap["simulated"]["breakeven_units"] is None


def test_sql_workbench_sandbox_security(client: TestClient):
    wb = client.get("/api/sql/workbench?dataset_id=vn_fashion_omni").json()
    assert len(wb["templates"]) == 10

    # Run all 10 curated SQL templates (including Market Basket Lift & Rolling Window)
    for tpl in wb["templates"]:
        r_ok = client.post("/api/sql/execute", json={"sql": tpl["sql"]})
        assert r_ok.status_code == 200
        assert r_ok.json()["row_count"] >= 1

    # Block destructive / write SQL statements
    for malicious in [
        "DROP TABLE orders;",
        "DELETE FROM skus WHERE 1=1;",
        "SELECT * FROM skus; DROP TABLE skus;",
        "PRAGMA writable_schema = 1;",
    ]:
        r_bad = client.post("/api/sql/execute", json={"sql": malicious})
        assert r_bad.status_code == 400


def test_predictive_forecast_scipy_stats_and_market_basket(client: TestClient):
    res = client.get("/api/predictive?dataset_id=vn_fashion_omni").json()

    # 1. 30-day Holt Seasonal Forecast + Fan intervals
    fc = res["forecast_30d"]
    assert fc["available"] is True
    assert len(fc["forecast"]) == 30
    s30 = fc["summary_30d"]
    assert s30["rev_p10"] <= s30["rev_p50"] <= s30["rev_p90"]
    assert s30["working_capital_needed"] > 0

    # 2. SciPy Hypothesis tests (Welch t-test & Chi-Square)
    tests = res["hypothesis_tests"]
    assert len(tests) >= 3
    for ht in tests:
        assert 0.0 <= ht["p_value"] <= 1.0

    # 3. Market Basket Lift & Bleeder Rescue Bundles
    bundles = res["market_basket_bundles"]
    assert len(bundles) >= 3
    assert any(b["is_bleeder_rescue"] and b["bundle_net_profit"] > 0 for b in bundles)
    assert all(b["lift"] > 1.0 for b in bundles)

    # 4. SPC Z-Score Anomalies
    anoms = res["anomalies"]
    assert len(anoms) >= 1
    assert anoms[0]["z_score"] >= 1.75


def test_messy_xlsx_import_and_report_export_roundtrip(client: TestClient):
    tpl_res = client.get("/api/export/template.xlsx")
    assert tpl_res.status_code == 200
    xlsx_bytes = tpl_res.content
    assert len(xlsx_bytes) > 2000

    imp_res = client.post(
        "/api/import",
        data={"dataset_name": "Shop Test Tháng 10"},
        files={"file": ("test_orders.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert imp_res.status_code == 200
    imp_json = imp_res.json()
    new_ds_id = imp_json["dataset_id"]
    assert imp_json["audit"]["dirty_numbers_cleaned"] >= 1
    assert imp_json["audit"]["dirty_dates_standardized"] >= 1

    # Verify overview & report export work on uploaded dataset
    ov = client.get(f"/api/overview?dataset_id={new_ds_id}")
    assert ov.status_code == 200
    rep = client.get(f"/api/export/report.xlsx?dataset_id={new_ds_id}")
    assert rep.status_code == 200
    assert len(rep.content) > 3000

    # Clean up temporary custom dataset
    del_res = client.delete(f"/api/datasets/{new_ds_id}")
    assert del_res.status_code == 200
