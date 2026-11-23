# Bản đồ địa hình 3D phường Yên Bái

Web hiển thị địa hình 3D từ mô hình độ cao, cùng 87 điểm trượt lở/nguy cơ trong bộ dữ liệu. Có thể xoay, thu phóng, tìm kiếm, lọc trạng thái, xem thông tin từng điểm và bật/tắt các lớp đường, công trình, mặt nước. Chế độ ảnh vệ tinh tải trực tuyến từ Esri World Imagery; nếu không truy cập được, ứng dụng trở về nền địa hình có sẵn.

## Chạy bằng Docker

Cần cài Docker và Docker Compose. Tại thư mục dự án:

```bash
docker compose up --build -d
```

Mở **http://localhost:18087**. Dừng ứng dụng bằng `docker compose down`. Cổng có thể đổi trong `compose.yaml` (ví dụ `8080:8000`). Lần build đầu cần tải image Python từ registry nếu chưa có sẵn.

Có thể thử trực tiếp khi đã cài Python 3: `python3 -m http.server 18087 --directory web`.

## Điều khiển bản đồ

- Cuộn chuột để phóng to tại vị trí con trỏ; nút +/− phóng to hoặc thu nhỏ từ tâm. Mức zoom từ 0,55× đến 16×.
- Kéo để xoay; giữ Shift và kéo hoặc kéo chuột phải để di chuyển. Trên thiết bị cảm ứng, chọn nút ✥ để chuyển sang chế độ di chuyển. Nút hình nhà đặt lại góc nhìn.
- Phóng đại không tạo thêm độ chi tiết thực so với ảnh và DEM nguồn; các lớp công trình và đường có thể làm thao tác chậm hơn khi bật.

## Dữ liệu và giới hạn

Thư mục `data/` chứa dữ liệu gốc và được giữ cục bộ, không đưa lên GitHub; nếu có sẵn, phần mô tả nằm trong `data/README.md`. Bản web sử dụng DEM WGS84 và lớp `truot_lo_phuong_Yen_Bai.gpkg`; tệp Excel 90 dòng chưa được đối chiếu và hợp nhất với 87 điểm trong lớp này. Điểm dùng màu theo trường trạng thái có sẵn, không biểu thị mức cảnh báo hiện tại. Đây không phải hệ thống cảnh báo thời gian thực; dữ liệu cần được kiểm chứng trước khi sử dụng cho quyết định an toàn.

Mô hình lấy mẫu DEM để chạy trong trình duyệt và phóng đại độ cao để dễ nhìn. Lớp ảnh vệ tinh cần Internet và WebGL; chất lượng ảnh tùy nguồn Esri, không làm tăng độ phân giải của DEM gốc. Ảnh được tải trực tiếp về trình duyệt và không đóng gói trong image Docker. Các lớp đường, công trình và mặt nước lấy từ OpenStreetMap trong `nen_phuong_Yen_Bai.gpkg`; chỉ các đối tượng có dữ liệu địa hình phù hợp được vẽ. Công trình được dựng theo dấu chân với chiều cao minh họa đồng nhất, không phải chiều cao thực. Dữ liệu gốc không có vị trí cây hoặc ảnh vệ tinh; ảnh vệ tinh được cung cấp trực tuyến. Các vị trí không có ô độ cao hợp lệ ở gần sẽ không vẽ trên địa hình nhưng vẫn có trong danh sách. Chưa tích hợp mưa, các vùng vết trượt vệ tinh, cờ IoT hoặc thông báo tự động.

Tệp `web/assets/data.json` chứa dữ liệu đã xử lý từ dữ liệu gốc (địa hình, vị trí trượt lở và các lớp bản đồ), được lưu trong kho mã và đóng gói sẵn trong image để ứng dụng chạy được mà không cần thư mục `data/`. Nếu dữ liệu gốc thay đổi, chạy `python3 scripts/prepare_data.py` với thư viện Pillow rồi build lại image. Quá trình build và chạy ứng dụng không cần Pillow.

## Dashboard khám phá dữ liệu

`dashboard.html` là báo cáo khám phá dữ liệu trong `data/` (tệp Excel, GeoPackage, raster, mưa) gồm các tab tổng quan, điểm trượt lở, đối chiếu Excel ↔ GeoPackage, vết trượt bão Yagi, mưa, địa hình & nền, chất lượng dữ liệu và bản đồ GeoGIS 3D (DEM 30 m với các lớp điểm, vết trượt, đường, mặt nước, đứt gãy). Mở trực tiếp bằng trình duyệt (cần Internet để tải Plotly). Tạo lại sau khi giải nén `data/du_lieu_phuong_Yen_Bai.rar` vào `data/du_lieu_phuong_Yen_Bai/`:

```bash
python scripts/build_dashboard.py
```

Cần pandas, pyarrow, openpyxl, geopandas, shapely, numpy và Pillow.

## Mô hình dự báo thử nghiệm

> Thử nghiệm – ngưỡng nháp, cần cơ quan chuyên môn xác nhận. Không dùng để ra quyết định an toàn.

Gói `model/` kết hợp hai phần: mô hình **mức độ dễ trượt** theo ô 30 m (Random Forest/hồi quy logistic, học từ vết trượt vệ tinh bão Yagi, kiểm định trên phường Yên Bái) và **ngưỡng mưa nháp** R0–R3 (mưa 24h/72h). Quy tắc trong `model/warning.py` + `model/config.json` ghép hai phần thành màu cờ (xanh/vàng/cam/đỏ, còi khi đỏ; thiếu số liệu mưa → xám).

```bash
python -m model.run_all            # bộ dữ liệu → mô hình → ngưỡng mưa → backtest
python -m pytest                   # kiểm thử
python scripts/build_dashboard.py  # cập nhật tab "Mô hình dự báo"
```

Đầu ra trong `model/outputs/`: `susceptibility_prob.tif`, `susceptibility_class.tif`, `flags.csv`/`flags.json` (87 điểm cờ và cấp), `metrics.json`, `thresholds.json`, `backtest.json`. Cần thêm scikit-learn, scipy, pytest.

Giới hạn: mọi nhãn đến từ một trận bão (Yagi, 09/2024); ngưỡng R3 được neo theo lượng mưa Yagi đến hết 09/09/2024 (một sự kiện); vết trượt vệ tinh chỉ có ở đất dốc ≥ 5° nên AUC trên toàn vùng (0,755) cao hơn AUC chỉ trên đất dốc (0,653); 87 điểm cờ không độc lập với vết Yagi; một chuỗi mưa chung cho cả phường. Thiết kế: `docs/superpowers/specs/2026-11-23-mo-hinh-du-bao-sat-lo-design.md`.
