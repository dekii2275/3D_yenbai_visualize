# Thiết kế: Mô hình dự báo sạt lở thử nghiệm – phường Yên Bái

Ngày: 2026-11-23 · Branch: `manh-explore-data`

## 1. Mục đích

Dự án là mô hình cảnh báo thiên tai cho cấp xã: sa bàn in 3D, cắm cờ tại các điểm sạt lở; hệ thống nhận dữ liệu (SMS / 3G-4G), có data logger, truyền xuống các cờ để đổi màu theo mức nguy cơ, bật còi khi nguy cơ cao.

Phần việc này tạo **con số quyết định màu của từng cờ**: xử lý dữ liệu và train thử mô hình dự báo sạt lở, ở dạng có thể chạy lại và đưa vào web / bộ điều khiển sau này.

Hướng đã chọn (người dùng chọn): **kết hợp** “ở đâu dễ trượt” (mô hình học từ dữ liệu) với “khi nào nguy hiểm” (ngưỡng mưa theo quy tắc).

## 2. Hiện trạng dữ liệu liên quan

- **Nhãn trượt lở có vị trí:** 904 vết trượt vệ tinh (lớp `vet_truot_ve_tinh_Yagi` trong `nen_phuong_Yen_Bai.gpkg`), 743 vết nằm trong vùng phủ DEM 30 m (Yên Bái 268, Nam Cường 254, Văn Phú 120, Âu Lâu 99, Yên Bình 2). Mọi vết đều thuộc một đợt ảnh (`DM_20240907`), ngày phát sinh 06–14/09/2024 — **chỉ một trận bão Yagi**.
- **87 điểm nguy cơ** (`truot_lo_phuong_Yen_Bai.gpkg`): không có ngày xảy ra (`thoi_gian_xay_ra`, `su_kien`… trống). 64/87 điểm nằm cách vết Yagi gần nhất < 100 m (trung vị 36 m) — nên **không độc lập** với nhãn Yagi.
- **Biến không gian sẵn có:** DEM, độ dốc, hướng dốc, hillshade, biên độ địa hình 300 m (UTM 48N, 289×224 ô 30 m); địa chất (22 vùng) và đứt gãy; OSM đường, sông, mặt nước, công trình.
- **Mưa:** mưa giờ 6 trạm 2021–2026 (`mua_gio_tram_quanh_phuong_2021_2026.parquet`), chuỗi tích luỹ 1 giờ–7 ngày (`mua_tich_luy_truot.parquet`, 2021-06 → 2026-11, đỉnh trùng trạm YBa084), mưa ngày 2 trạm 2011–2024. **Không có toạ độ trạm** trong dữ liệu.

Hệ quả: học được “ở đâu” (743 vết); **không học được “khi nào”** từ dữ liệu (1 sự kiện) → phần thời gian dùng ngưỡng quy tắc.

## 3. Mục tiêu / không làm / tránh

**Mục tiêu**
1. Bộ dữ liệu huấn luyện theo ô 30 m, tái tạo được bằng script từ `data/`.
2. Mô hình mức độ dễ trượt (susceptibility) cho mọi ô, có đánh giá trung thực (kiểm định theo không gian).
3. Ngưỡng mưa nháp 4 mức, kèm bằng chứng từ chuỗi mưa.
4. Quy tắc cảnh báo: (mức dễ trượt của điểm cờ) × (mức mưa) → xanh / vàng / cam / đỏ (+ còi), là một hàm thuần có test.
5. Chạy lại (backtest) quy tắc trên chuỗi mưa 2021–2026: Yagi phải lên đỏ; đếm số ngày cam/đỏ để biết mức báo động giả.
6. Báo cáo kết quả (tab mới trong `dashboard.html`).

**Không làm lần này:** hệ thống thời gian thực; phần cứng, SMS, ESP32; deep learning; đối chiếu lại danh sách điểm Excel ↔ GPKG (việc riêng); ngưỡng chính thức.

**Tránh (dù chạy được vẫn coi là hỏng)**
- Trình bày ngưỡng mưa như ngưỡng chính thức. Mọi đầu ra phải ghi “thử nghiệm – cần cơ quan chuyên môn xác nhận”.
- Độ chính xác ảo do rò rỉ: dùng thuộc tính của chính vết Yagi (mưa max 24h, NDVI, dBSI, coherence…) làm biến; chia train/test ngẫu nhiên khiến ô kề nhau rơi vào cả hai phía.
- Dùng 87 điểm như bằng chứng độc lập cho độ chính xác (chúng trùng vị trí với vết Yagi).
- Quy tắc làm cờ đỏ thường xuyên (báo động giả nhiều thì người dân bỏ qua).

## 4. Các hướng đã cân nhắc

| Hướng | Nội dung | Đánh đổi |
|---|---|---|
| **Kết hợp (đã chọn)** | Train mô hình dễ trượt theo ô + ngưỡng mưa quy tắc → ma trận cảnh báo | Khớp luồng “mưa → đổi màu cờ”; phần ngưỡng là nháp |
| Chỉ bản đồ nguy cơ | Chỉ mô hình dễ trượt | Chắc hơn, nhưng cờ không đổi theo mưa |
| Mô hình theo thời gian học từ mưa | Phân loại ngày có/không trượt | Chỉ 1 sự kiện → không train được thật |

## 5. Thiết kế

### 5.1 Bộ dữ liệu (đơn vị: ô DEM 30 m, vùng phủ DEM)
- **Nhãn dương:** ô có tâm nằm trong (hoặc giao) đa giác vết Yagi.
- **Nhãn âm:** lấy mẫu ngẫu nhiên các ô cách vết bất kỳ ≥ 60 m, tỉ lệ khoảng 1 dương : 3–5 âm; loại ô mặt nước lớn (sông Hồng) khỏi cả hai phía.
- **Biến** (chỉ lấy từ nền, không lấy từ vết): cao độ, độ dốc, sin/cos hướng dốc, biên độ địa hình 300 m, độ cong và TPI (tính từ DEM), khoảng cách tới đường / sông-mặt nước / đứt gãy, nhóm đá và đơn vị địa chất (one-hot), mật độ công trình (số công trình trong bán kính 100–200 m).

### 5.2 Mô hình dễ trượt
- So sánh **hồi quy logistic** (dễ giải thích) và **Random Forest** (scikit-learn); chọn cái tốt hơn theo kiểm định không gian, ưu tiên mô hình đơn giản nếu chênh lệch nhỏ.
- **Kiểm định không gian:** (a) train trên các phường khác, test trên phường Yên Bái; (b) cross-validation theo khối không gian (khối ~1 km). Báo AUC-ROC, AUC-PR, và % vết rơi vào nhóm nguy cơ cao/rất cao.
- **Phân cấp:** xác suất → 4 cấp theo diện tích: Rất cao (5% diện tích nguy hiểm nhất), Cao (10% kế), Trung bình (25% kế), Thấp (còn lại).
- **Kiểm tra phụ (không phải bằng chứng độc lập):** cấp dễ trượt của 87 điểm cờ.
- Xuất: raster xác suất + cấp (GeoTIFF), độ quan trọng của biến.

### 5.3 Ngưỡng mưa nháp
- Nguồn: chuỗi `mua_tich_luy_truot.parquet` (một chuỗi cho cả phường — hợp với thử nghiệm một xã, một nguồn số liệu mưa).
- Chỉ số: mưa 24h và mưa 72h (3 ngày).
- 4 mức R0–R3 đặt từ phân vị của chuỗi (ví dụ R1 ≈ P99, R2 ≈ P99.9 của mưa 72h) và neo với Yagi (R3 phải đạt trước/đúng 09/09/2024); đối chiếu với cấp độ rủi ro do mưa trong Quyết định 18/2021/QĐ-TTg nếu tra được văn bản, ghi rõ nguồn.
- Xuất `thresholds.json` gồm giá trị, cách tính, cảnh báo “nháp”.

### 5.4 Quy tắc cảnh báo (đề xuất, chỉnh được trong config)

| Mức mưa \ Cấp dễ trượt | Thấp | Trung bình | Cao | Rất cao |
|---|---|---|---|---|
| R0 | xanh | xanh | xanh | xanh |
| R1 | xanh | xanh | vàng | vàng |
| R2 | xanh | vàng | cam | cam |
| R3 | vàng | cam | đỏ + còi | đỏ + còi |

Cài đặt là một hàm thuần `warning_level(cap_de_truot, mua_24h, mua_72h, thresholds) → (mau, coi)`, có unit test — chính hàm này sau này web / bộ điều khiển dùng lại.

### 5.5 Backtest
Chạy quy tắc theo giờ trên chuỗi 2021–2026 cho 87 điểm cờ: số giờ / ngày ở mỗi màu, các đợt đỏ; kiểm tra Yagi lên đỏ và đợt lớn thứ hai (01/10/2025, 325 mm/72h) ra sao.

### 5.6 Bố trí mã và đầu ra
- `model/` : `build_dataset.py`, `train_susceptibility.py`, `rain_thresholds.py`, `warning.py`, `backtest.py`, `config.json` (ngưỡng, ma trận).
- `model/outputs/` (commit, kích thước nhỏ): `susceptibility.tif`, `flags.csv` / `flags.json` (mã điểm, toạ độ, xác suất, cấp), `metrics.json`, `thresholds.json`, `backtest.json`.
- `tests/test_warning.py` cho quy tắc cảnh báo.
- Dashboard: thêm tab “Mô hình dự báo” (bản đồ cấp dễ trượt, chỉ số kiểm định, ngưỡng, kết quả backtest, ô thử “nhập mưa → màu cờ”).

## 6. Ràng buộc
- `data/` không lên Git; script đọc từ `data/du_lieu_phuong_Yen_Bai/du_lieu/` như `prepare_data.py`.
- Hệ toạ độ làm việc UTM 48N (EPSG:32648); DEM UTM 30 m là lưới chuẩn.
- Python 3.12 cục bộ: pandas, geopandas, shapely, numpy, Pillow có sẵn; scikit-learn cần kiểm tra / cài.

## 7. Quyết định của tôi (người dùng có thể sửa)
- Dùng toàn bộ 743 vết trong vùng phủ DEM (không chỉ 268 vết trong phường) để có đủ dữ liệu và để test riêng trên Yên Bái.
- Một chuỗi mưa cho cả phường (không có toạ độ trạm để nội suy).
- Ma trận cảnh báo và cách chia 4 cấp như trên.
- Đầu ra commit vào repo; báo cáo đặt trong dashboard hiện có.
- Giờ thiếu số liệu mưa (chuỗi tích luỹ có khoảng trống) được tính là “không có số liệu” (màu xám), không coi là R0, và được đếm riêng trong backtest.
- Ranh giới các phường lân cận lấy từ `xa_Lao_Cai.gpkg` để chia train/test.

## 8. Để người làm quyết định
Bán kính mật độ công trình, cách tính độ cong / TPI, siêu tham số mô hình, cách lấy mẫu âm cụ thể (trong khoảng nêu trên), cách vẽ tab dashboard.
