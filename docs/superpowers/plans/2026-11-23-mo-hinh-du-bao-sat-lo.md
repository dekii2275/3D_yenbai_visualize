# Mô hình dự báo sạt lở thử nghiệm – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ dữ liệu trong `data/`, train mô hình mức độ dễ trượt theo ô 30 m, đặt ngưỡng mưa nháp 4 mức, ghép thành quy tắc màu cờ, backtest 2021–2026 và báo cáo trong dashboard.

**Architecture:** Gói `model/` gồm các module nhỏ chạy tuần tự (đặc trưng → bộ dữ liệu → mô hình → ngưỡng mưa → backtest), mỗi bước ghi JSON/GeoTIFF vào `model/outputs/`. Quy tắc cảnh báo là hàm thuần trong `model/warning.py`, đọc ma trận từ `model/config.json`. `scripts/build_dashboard.py` đọc `model/outputs/` để vẽ tab “Mô hình dự báo”.

**Tech Stack:** Python 3.12, numpy, pandas, geopandas, shapely 2, scipy.ndimage, scikit-learn 1.9, Pillow (đọc/ghi GeoTIFF), pytest; Plotly trong dashboard.

**Spec:** `docs/superpowers/specs/2026-11-23-mo-hinh-du-bao-sat-lo-design.md`

## Global Constraints

- Dữ liệu đọc từ `data/du_lieu_phuong_Yen_Bai/du_lieu/` (hằng `SRC` trong `model/paths.py`); `data/` không commit.
- Hệ toạ độ làm việc EPSG:32648; lưới chuẩn = `DEM_30m_phuong_Yen_Bai_UTM48N.tif` (289×224, ô 30 m).
- Mọi ngẫu nhiên dùng `random_state=42`.
- Biến mô hình **không** được lấy từ thuộc tính vết Yagi (`max_24h_mm`, `max_72h_mm`, `rdNDVI`, `dBSI`, `dS1_dB`, `dcoh`, `coh_truoc`, `diem_tb`, `so_pixel`, `cap_mua`…).
- Cấp dễ trượt: `["Thấp", "Trung bình", "Cao", "Rất cao"]` = < P60, P60–P85, P85–P95, ≥ P95 của xác suất trên các ô hợp lệ (không tính mặt nước).
- Màu: `"xanh" | "vàng" | "cam" | "đỏ" | "xám"`; còi chỉ khi `"đỏ"`.
- Mọi đầu ra ngưỡng/cảnh báo mang chuỗi đúng: `"Thử nghiệm – ngưỡng nháp, cần cơ quan chuyên môn xác nhận"`.
- Chạy Python bằng `python -I`; test bằng `python -I -m pytest`.

## Review Focus

1. Giờ thiếu số liệu mưa (NaN) → cờ `"xám"`, không phải `"xanh"` — test ở Task 1.
2. Điểm cờ rơi vào ô nodata/mặt nước → cấp `None` → cờ `"xám"`, không lỗi — test ở Task 1 và Task 3.
3. Lượng mưa đúng bằng ngưỡng → thuộc mức đó (so sánh `>=`) — test ở Task 1.
4. Ô mặt nước lớn (sông Hồng) không được xếp “Rất cao” — raster cấp ghi nodata 255 ở đó — test ở Task 3.
5. Rò rỉ nhãn: danh sách biến chứa thuộc tính vết Yagi — test chặn ở Task 3.

---

### Task 1: Quy tắc cảnh báo

**Files:**
- Create: `model/__init__.py` (rỗng), `model/paths.py`, `model/config.json`, `model/warning.py`
- Test: `tests/test_warning.py`

**Interfaces:**
- Produces:
  - `model/paths.py`: `ROOT: Path`, `SRC: Path`, `OUT: Path` (= `ROOT/'model'/'outputs'`), `WORK: Path` (= `ROOT/'model'/'work'`), `CONFIG: Path`.
  - `CAP = ["Thấp", "Trung bình", "Cao", "Rất cao"]`, `NOTE = "Thử nghiệm – ngưỡng nháp, cần cơ quan chuyên môn xác nhận"` trong `model/warning.py`.
  - `load_config(path: Path = CONFIG) -> dict`
  - `rain_level(mua_24h: float | None, mua_72h: float | None, thresholds: dict) -> int | None` — `thresholds = {"mua_24h_mm": [r1, r2, r3], "mua_72h_mm": [r1, r2, r3]}`; trả max mức của hai chỉ số; `None` nếu cả hai thiếu (NaN/None); nếu chỉ một thiếu thì dùng chỉ số còn lại.
  - `warning_level(cap: str | None, mua_24h, mua_72h, config: dict) -> dict` → `{"mau": str, "coi": bool, "muc_mua": int | None}`.
- `model/config.json`: `{"ghi_chu": NOTE, "nguong": {"mua_24h_mm": null, "mua_72h_mm": null}, "ma_tran": {"R0": ["xanh","xanh","xanh","xanh"], "R1": ["xanh","xanh","vàng","vàng"], "R2": ["xanh","vàng","cam","cam"], "R3": ["vàng","cam","đỏ","đỏ"]}}` (cột theo thứ tự `CAP`; `nguong` điền ở Task 4).

- [ ] **Step 1: Viết test thất bại** — `tests/test_warning.py` dùng config cố định trong test (`thresholds = {"mua_24h_mm": [50, 100, 200], "mua_72h_mm": [100, 200, 400]}` + ma trận ở trên):
  - `test_rain_level_takes_max`: `rain_level(60, 50, t) == 1`; `rain_level(10, 450, t) == 3`.
  - `test_rain_level_boundary_inclusive`: `rain_level(50, 0, t) == 1`; `rain_level(49.9, 99.9, t) == 0`.
  - `test_rain_level_missing`: `rain_level(None, float("nan"), t) is None`; `rain_level(float("nan"), 250, t) == 2`.
  - `test_matrix_cells`: `warning_level("Cao", 0, 250, cfg)["mau"] == "cam"`; `warning_level("Thấp", 0, 450, cfg)["mau"] == "vàng"`; `warning_level("Rất cao", 210, 0, cfg) == {"mau": "đỏ", "coi": True, "muc_mua": 3}`.
  - `test_missing_rain_grey`: `warning_level("Rất cao", None, None, cfg) == {"mau": "xám", "coi": False, "muc_mua": None}`.
  - `test_unknown_cap`: `warning_level(None, 300, 500, cfg)["mau"] == "xám"`; `warning_level("abc", 1, 1, cfg)` raises `ValueError`.
  - `test_config_file_matrix`: `load_config()["ma_tran"]["R3"] == ["vàng","cam","đỏ","đỏ"]` và `load_config()["ghi_chu"] == NOTE`.
- [ ] **Step 2: Chạy** `python -I -m pytest tests/test_warning.py -v` → FAIL (module chưa có).
- [ ] **Step 3: Cài đặt** `model/paths.py`, `model/config.json`, `model/warning.py` theo Interfaces. `tests/conftest.py` thêm `ROOT` vào `sys.path` (vì `-I` bỏ thư mục hiện tại).
- [ ] **Step 4: Chạy lại** → PASS 7 test.
- [ ] **Step 5: Commit** `feat(model): add warning rule and config`; thêm `/model/work/` vào `.gitignore`.

### Task 2: Đặc trưng raster và bộ dữ liệu huấn luyện

**Files:**
- Create: `model/features.py`, `model/build_dataset.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `model/paths.py`.
- Produces:
  - `@dataclass Grid: dem: np.ndarray; west: float; north: float; cell: float; xs: np.ndarray; ys: np.ndarray` (tâm ô), `shape` property; `load_grid(src: Path) -> Grid` (nodata → NaN).
  - `cells_from_geoms(grid: Grid, geoms, step_m: float = 10) -> np.ndarray[bool]` — đánh dấu ô chạm hình học (đa giác: tâm ô nằm trong **hoặc** ô chứa centroid; đường: điểm làm dày mỗi `step_m`).
  - `distance_m(mask: np.ndarray, cell: float) -> np.ndarray` — `scipy.ndimage.distance_transform_edt(~mask) * cell`.
  - `tpi(dem: np.ndarray, size: int) -> np.ndarray` — `dem - uniform_filter` (bỏ qua NaN bằng lọc tử/mẫu).
  - `curvature(dem: np.ndarray, cell: float) -> np.ndarray` — Laplacian âm (lồi > 0).
  - `feature_stack(src: Path, grid: Grid) -> dict[str, np.ndarray]` với khoá đúng: `cao_do, do_doc, sin_huong, cos_huong, bien_do_300m, do_cong, tpi_330m, kc_duong_m, kc_nuoc_m, kc_dut_gay_m, mat_do_nha_150m` + one-hot `da_bien_chat, da_tram_tich_de_tu, da_carbonat, da_khac` (từ `nhom_da` của lớp `dia_chat`). Đường = `osm_roads` mọi loại; nước = `osm_waterways` + `osm_water_a`; mật độ nhà = số centroid `osm_buildings_a` trong đĩa bán kính 150 m (5 ô).
  - `FEATURES: list[str]` (đúng thứ tự khoá `feature_stack`) và `FORBIDDEN = ["max_24h_mm","max_72h_mm","rdNDVI","dBSI","dS1_dB","dcoh","coh_truoc","diem_tb","so_pixel","cap_mua"]` khai báo trong `model/features.py`.
  - `masks(src: Path, grid: Grid) -> dict` khoá `positive` (ô vết Yagi, lớp `vet_truot_ve_tinh_Yagi`), `water` (ô tâm trong `osm_water_a` fclass riverbank/water), `valid` (DEM hữu hạn và không water), `ward` (mảng chuỗi tên phường từ `xa_Lao_Cai.gpkg`, `""` ngoài mọi phường).
  - `build_dataset(src: Path, seed: int = 42, neg_ratio: int = 4, buffer_m: float = 60) -> pd.DataFrame` cột `row, col, x, y, nhan, phuong` + mọi khoá của `feature_stack`; âm lấy ngẫu nhiên trong `valid & ~positive & distance_m(positive) >= buffer_m`. `python -I -m model.build_dataset` ghi `WORK/dataset.parquet` và in số dương/âm theo phường.
- [ ] **Step 1: Viết test thất bại** `tests/test_features.py`:
  - `test_distance_m`: mask 5×5 chỉ ô giữa True, cell 30 → `distance_m(...)[2, 4] == 60` và `[2, 2] == 0`.
  - `test_tpi_flat_zero`: `tpi(np.full((9, 9), 5.0), 3)` toàn 0.
  - `test_curvature_sign`: đỉnh nhọn (giữa cao hơn) → `curvature(...)[c, c] > 0`.
  - `test_cells_from_small_polygon`: lưới 3×3 ô 30 m, đa giác vuông 10 m nằm lệch tâm trong ô (1,1) → chỉ `(1,1)` True.
  - `test_dataset_real` (bỏ qua bằng `pytest.mark.skipif(not SRC.exists())`): `df = build_dataset(SRC)`; `df.nhan.sum() > 500`; `(df.nhan == 0).sum() >= 3 * df.nhan.sum()`; `df[FEATURES].isna().sum().sum() == 0` sau khi điền khoảng cách; `"Yên Bái" in set(df.phuong)`; không có cột nào trong danh sách cấm ở Global Constraints.
- [ ] **Step 2: Chạy** `python -I -m pytest tests/test_features.py -v` → FAIL.
- [ ] **Step 3: Cài đặt** `model/features.py`, `model/build_dataset.py` theo Interfaces. Ô có biến NaN (rìa DEM) bị loại khỏi `valid`.
- [ ] **Step 4: Chạy lại** → PASS; chạy `python -I -m model.build_dataset` và ghi lại số dương/âm.
- [ ] **Step 5: Commit** `feat(model): build feature rasters and training dataset`.

### Task 3: Mô hình dễ trượt, đánh giá không gian, xuất kết quả

**Files:**
- Create: `model/train_susceptibility.py`, `model/geotiff.py`
- Test: `tests/test_train.py`

**Interfaces:**
- Consumes: `build_dataset`, `feature_stack`, `masks`, `load_grid`, `FEATURES`, `FORBIDDEN` (Task 2); `CAP` (Task 1).
- Produces:
  - `spatial_blocks(x: np.ndarray, y: np.ndarray, size_m: float = 1000) -> np.ndarray[int]`.
  - `make_models() -> dict[str, sklearn estimator]`: `"logistic"` = `Pipeline(StandardScaler, LogisticRegression(class_weight="balanced", max_iter=2000))`; `"random_forest"` = `RandomForestClassifier(n_estimators=400, min_samples_leaf=5, class_weight="balanced_subsample", n_jobs=-1, random_state=42)`.
  - `evaluate(model, df: pd.DataFrame) -> dict` → `{"holdout_yen_bai": {"auc_roc", "auc_pr", "n_pos", "n_neg"}, "block_cv": {"auc_roc_mean", "auc_roc_std", "auc_pr_mean"}}`; holdout = train `phuong != "Yên Bái"`, test `phuong == "Yên Bái"`; block CV = `GroupKFold(5)` theo `spatial_blocks`.
  - `choose(results: dict) -> str` — `"random_forest"` nếu AUC-ROC holdout của RF lớn hơn logistic **> 0.02**, ngược lại `"logistic"`.
  - `classify(prob: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, list[float]]` — mảng uint8 0..3 theo P60/P85/P95 trên `prob[valid]`, 255 ngoài `valid`; trả kèm 3 ngưỡng.
  - `write_geotiff(path: Path, arr: np.ndarray, template: Path, nodata: float) -> None` — Pillow, sao chép tag 33550, 33922, 34735, 34736, 34737 từ template, đặt 42113 = nodata.
  - `python -I -m model.train_susceptibility` ghi `OUT/susceptibility_prob.tif` (float32, nodata −9999), `OUT/susceptibility_class.tif` (uint8, nodata 255), `OUT/metrics.json` (`models`, `chosen`, `cutoffs`, `importance` — RF `feature_importances_` hoặc |hệ số| chuẩn hoá của logistic, `yen_bai_scar_cells_by_class`, `flags_by_class`), `OUT/flags.csv` + `OUT/flags.json` (87 điểm: `ma_vi_tri, ten_diem, trang_thai, lon, lat, xac_suat, cap`; điểm rơi vào ô ngoài `valid` lấy ô hợp lệ gần nhất trong 1 ô, nếu không có → `xac_suat=None, cap=None`).
- [ ] **Step 1: Viết test thất bại** `tests/test_train.py`:
  - `test_no_leakage`: `set(FEATURES).isdisjoint(FORBIDDEN)`.
  - `test_classify_proportions`: `prob = np.linspace(0, 1, 10000).reshape(100, 100)`, `valid` toàn True trừ hàng 0 → tỉ lệ lớp 3 ≈ 0.05 (±0.01), lớp 2 ≈ 0.10, lớp 1 ≈ 0.25; `classes[0].max() == 255`.
  - `test_spatial_blocks`: `spatial_blocks(np.array([0, 999, 1000]), np.array([0, 0, 0]))` → hai phần tử đầu cùng khối, phần tử cuối khác.
  - `test_choose`: `choose({"logistic": {"holdout_yen_bai": {"auc_roc": .80}}, "random_forest": {"holdout_yen_bai": {"auc_roc": .81}}}) == "logistic"`; với RF 0.83 → `"random_forest"`.
  - `test_outputs_real` (skipif không có `SRC`), chạy sau khi train: `metrics.json` có `chosen` ∈ hai tên; `holdout_yen_bai.auc_roc` trong (0.5, 1]; `susceptibility_class.tif` đọc lại có shape (224, 289) và giá trị ⊂ {0,1,2,3,255}; mọi ô mặt nước = 255; `flags.json` có 87 phần tử, `cap` ∈ `CAP` hoặc `None`.
- [ ] **Step 2: Chạy** `python -I -m pytest tests/test_train.py -v` → FAIL.
- [ ] **Step 3: Cài đặt** theo Interfaces.
- [ ] **Step 4: Chạy** `python -I -m model.train_susceptibility` rồi `python -I -m pytest tests/test_train.py -v` → PASS; ghi lại AUC hai mô hình.
- [ ] **Step 5: Commit** `feat(model): train susceptibility model with spatial validation` kèm `model/outputs/`.

### Task 4: Ngưỡng mưa nháp

**Files:**
- Create: `model/rain_thresholds.py`
- Modify: `model/config.json` (điền `nguong`)
- Test: `tests/test_rain.py`

**Interfaces:**
- Consumes: `NOTE`, `load_config` (Task 1).
- Produces:
  - `load_rain(src: Path) -> pd.DataFrame` — index giờ, cột `mua_24h` (= `"1 ngày"`), `mua_72h` (= `"3 ngày"`) từ `mua_tich_luy_truot.parquet`.
  - `draft_thresholds(rain: pd.DataFrame) -> dict` — mỗi chỉ số: R1 = P99, R2 = P99.9, R3 = P99.99 của các giờ có số liệu, làm tròn xuống bội 10 mm; trả `{"mua_24h_mm": [...], "mua_72h_mm": [...], "cach_tinh": "...", "ghi_chu": NOTE, "so_ngay_vuot": {"mua_24h_mm": [n1,n2,n3], "mua_72h_mm": [...]}, "yagi_dinh": {"mua_24h": ..., "mua_72h": ...}}`.
  - `python -I -m model.rain_thresholds` ghi `OUT/thresholds.json` và cập nhật `nguong` trong `model/config.json`.
- [ ] **Step 1: Viết test thất bại** `tests/test_rain.py`:
  - `test_draft_rounding`: chuỗi tổng hợp `np.arange(0, 10000)` (mm) cho cả hai cột → `[9890, 9980, 9990]`.
  - `test_thresholds_real` (skipif): R1 < R2 < R3 cho cả hai chỉ số; `yagi_dinh.mua_72h >= mua_72h_mm[2]`; `ghi_chu == NOTE`.
- [ ] **Step 2: Chạy** `python -I -m pytest tests/test_rain.py -v` → FAIL.
- [ ] **Step 3: Cài đặt**; tra Quyết định 18/2021/QĐ-TTg (cấp độ rủi ro do mưa lớn/sạt lở) bằng web search, ghi giá trị và nguồn vào `thresholds.json["doi_chieu"]`; nếu không xác minh được thì ghi `"chưa đối chiếu"`.
- [ ] **Step 4: Chạy** `python -I -m model.rain_thresholds` rồi test → PASS.
- [ ] **Step 5: Commit** `feat(model): draft rainfall thresholds`.

### Task 5: Backtest quy tắc trên chuỗi mưa 2021–2026

**Files:**
- Create: `model/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `rain_level`, `warning_level`, `load_config`, `CAP` (Task 1); `load_rain` (Task 4); `OUT/flags.json` (Task 3).
- Produces:
  - `hourly_levels(rain: pd.DataFrame, thresholds: dict) -> pd.Series` (giá trị 0–3 hoặc NaN).
  - `colour_hours(levels: pd.Series, config: dict) -> pd.DataFrame` — index giờ, cột theo `CAP`, giá trị màu.
  - `red_episodes(colours: pd.Series, rain: pd.DataFrame) -> list[dict]` — các đợt đỏ liên tục (gộp nếu cách nhau < 24 giờ): `{"bat_dau", "ket_thuc", "so_gio", "mua_72h_max"}`.
  - `run_backtest(rain, flags: list[dict], config) -> dict` → `{"so_gio": {cap: {mau: n}}, "so_ngay_co_mau": {cap: {mau: n}}, "dot_do": {cap: [...]}, "yagi": {cap: mau cao nhất 2024-09-08..2024-09-10}, "dot_2025_10_01": {cap: mau cao nhất 2025-09-29..2025-10-01}, "gio_thieu_so_lieu": n, "so_co_theo_cap": {cap: n}, "ghi_chu": NOTE}`. Thứ tự “cao nhất”: xám < xanh < vàng < cam < đỏ.
  - `python -I -m model.backtest` ghi `OUT/backtest.json`.
- [ ] **Step 1: Viết test thất bại** `tests/test_backtest.py`:
  - `test_red_episode_merge`: chuỗi màu 72 giờ có đỏ ở giờ 0–2 và 10–12 → 1 đợt; thêm đỏ ở giờ 50 → 2 đợt.
  - `test_missing_hours_grey`: mưa NaN ở 3 giờ → `colour_hours` cho `"xám"` ở 3 giờ đó với mọi cấp.
  - `test_backtest_real` (skipif): `yagi["Rất cao"] == "đỏ"`; `so_ngay_co_mau["Rất cao"]["đỏ"] <= 10`.
- [ ] **Step 2: Chạy** `python -I -m pytest tests/test_backtest.py -v` → FAIL.
- [ ] **Step 3: Cài đặt** theo Interfaces.
- [ ] **Step 4: Chạy** `python -I -m model.backtest` rồi toàn bộ `python -I -m pytest -v` → PASS.
- [ ] **Step 5: Commit** `feat(model): backtest warning rule on 2021-2026 rainfall`.

### Task 6: Tab “Mô hình dự báo” trong dashboard + hướng dẫn chạy

**Files:**
- Create: `model/run_all.py`
- Modify: `scripts/build_dashboard.py`, `scripts/dashboard_template.html`, `README.md`

**Interfaces:**
- Consumes: mọi tệp trong `OUT/` (Task 3–5), `model/config.json`.
- Produces:
  - `python -I -m model.run_all` chạy lần lượt build_dataset → train_susceptibility → rain_thresholds → backtest.
  - `build_dashboard.py` thêm khoá `model` vào DATA: `metrics`, `thresholds`, `backtest`, `config`, `flags`, và lưới cấp dễ trượt (`susceptibility_class.tif`, 255 → null) cùng hệ trục km với `scene`; nếu `OUT/metrics.json` chưa có thì `model = null` và tab hiển thị “Chưa chạy mô hình”.
  - Tab `data-tab="model"` (đặt trước tab GeoGIS 3D): KPI (mô hình được chọn, AUC holdout Yên Bái, AUC block-CV, % ô vết Yagi ở Yên Bái thuộc Cao/Rất cao); bản đồ heatmap cấp dễ trượt + điểm cờ; bar độ quan trọng biến; bảng so sánh hai mô hình; bảng ngưỡng (kèm `NOTE` hiển thị rõ); bảng backtest (số ngày theo màu × cấp, các đợt đỏ); khung thử “nhập mưa 24h/72h → màu từng cờ” dùng bản JS của `rain_level`/`warning_level` đọc `config` (cùng quy tắc `>=`, NaN → xám).
  - Tab 3D: thêm lựa chọn tô màu “Cấp dễ trượt”.
- [ ] **Step 1:** Cài đặt `model/run_all.py`; chạy `python -I -m model.run_all` → in đủ 4 bước, không lỗi.
- [ ] **Step 2:** Sửa `build_dashboard.py` + template; chạy `python -I scripts/build_dashboard.py` → ghi `dashboard.html`.
- [ ] **Step 3:** Mở dashboard trong trình duyệt: tab mới hiển thị đủ phần, không lỗi console; khung thử với 24h=0, 72h=1000 cho cờ “Rất cao” ra đỏ, ô trống ra xám; tab 3D đổi được sang “Cấp dễ trượt”.
- [ ] **Step 4:** README thêm mục “Mô hình dự báo thử nghiệm” (cách chạy, đầu ra, cảnh báo `NOTE`, giới hạn: chỉ một sự kiện Yagi, 87 điểm không độc lập).
- [ ] **Step 5: Commit** `feat(dashboard): add trial prediction model tab`.
