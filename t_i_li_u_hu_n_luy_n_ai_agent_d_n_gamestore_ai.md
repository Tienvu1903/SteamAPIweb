---
project_name: "GAMESTORE AI"
document_type: "AI_Training_Knowledge_Base_and_SOP"
version: "2.0"
platforms: ["Steam PC", "Nintendo Switch eShop"]
root_directory: "E:\\Steam_Machine_Learning\\Game_data"
data_directory: "E:\\Steam_Machine_Learning\\Game_data\\data\\cleaned_verified"
python_executable_admin: "C:\\Users\\ADMIN\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe"
---

# TÀI LIỆU TRI THỨC & HUẤN LUYỆN AI AGENT — DỰ ÁN GAMESTORE AI
*(Bản đầy đủ: Chuẩn hóa dữ liệu, luồng thực thi Pipeline, toàn bộ câu lệnh CMD và Kịch bản xử lý cho AI Agent)*

---

## PHẦN 1: TỔNG HỢP NHANH CÁC FILE CẦN CHẠY VÀ CÂU LỆNH CMD ĐẦY ĐỦ
*(Tóm tắt dành cho người mới hoặc Agent cần trích xuất lệnh nhanh: Xem Mục 1.3, 1.4 và Phần 4 bắt đầu từ Bước 0)*

### 1.1. Danh sách 3 File Code Python (`.py`) BẮT BUỘC chạy theo đúng thứ tự
Hệ thống gồm 3 file thực thi chính phải được chạy tuần tự từ 1 đến 3 (lưu ý: trong kiến trúc dự án không có file số 2):

1. **File chạy số 1:** `1_price_prediction_pipeline.py`
   * **Chức năng:** Chạy để huấn luyện mô hình và dự báo giá game trong 3 tháng tới.
2. **File chạy số 2:** `3_build_recommendation_system.py`
   * **Chức năng:** Chạy để tạo hệ thống gợi ý game cá nhân hóa cho từng User.
3. **File chạy số 3:** `4_web_app.py`
   * **Chức năng:** Chạy để mở giao diện trang Web (Streamlit Dashboard).

### 1.2. Danh sách 7 File Dữ liệu (`.csv`) trong thư mục `data/cleaned_verified/`

| STT | Tên File CSV | Phân loại | Nguồn gốc / Thời điểm sinh ra | Mô tả dữ liệu |
| :--- | :--- | :--- | :--- | :--- |
| **CSV 1** | `steam_users_profile_verified.csv` | Dữ liệu đầu vào (Input) | Có sẵn | Dữ liệu hồ sơ người dùng Steam |
| **CSV 2** | `steam_user_owned_games_verified.csv` | Dữ liệu đầu vào (Input) | Có sẵn | Dữ liệu kho game người dùng đã mua / đang sở hữu |
| **CSV 3** | `master_price_predicted.csv` | Dữ liệu đầu ra (Output) | Sinh ra sau khi chạy File 1 (`1_price_prediction_pipeline.py`) | Bảng giá hiện tại và giá dự báo trong 3 tháng tới |
| **CSV 4** | `ml_price_tournament_leaderboard.csv` | Dữ liệu đầu ra (Output) | Sinh ra sau khi chạy File 1 (`1_price_prediction_pipeline.py`) | Bảng xếp hạng thi đấu của 3 mô hình dự báo giá |
| **CSV 5** | `master_recommendations_ready.csv` | Dữ liệu đầu ra (Output) | Sinh ra sau khi chạy File 2 (`3_build_recommendation_system.py`) | Dữ liệu tổng hợp phục vụ hiển thị lên trang Web |
| **CSV 6** | `user_personalized_recommendations.csv` | Dữ liệu đầu ra (Output) | Sinh ra sau khi chạy File 2 (`3_build_recommendation_system.py`) | Danh sách gợi ý game riêng cho từng User |
| **CSV 7** | `ml_recommendation_structures_report.csv` | Dữ liệu đầu ra (Output) | Sinh ra sau khi chạy File 2 (`3_build_recommendation_system.py`) | Báo cáo kết quả đánh giá 3 cấu trúc gợi ý |

### 1.3. Trọn bộ câu lệnh CMD chạy từ A đến Z (Dùng trên máy tính gốc của ADMIN)
*Chỉ cần copy và dán lần lượt từ trên xuống dưới vào cửa sổ CMD là chạy được ngay:*

```cmd
# Bước 1: Chuyển sang ổ đĩa E và vào đúng thư mục chứa dự án
E:
cd E:\Steam_Machine_Learning\Game_data

# Bước 2: Nâng cấp công cụ cài đặt pip
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install --upgrade pip

# Bước 3: Cài đặt toàn bộ 10 thư viện cần thiết (Lệnh gộp 1 dòng)
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install pandas numpy scikit-learn scipy joblib requests streamlit openpyxl matplotlib seaborn

# Bước 4: Chạy file 1_price_prediction_pipeline.py (Huấn luyện AI dự báo giá)
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe E:\Steam_Machine_Learning\Game_data\1_price_prediction_pipeline.py

# Bước 5: Chạy file 3_build_recommendation_system.py (Huấn luyện AI gợi ý game)
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe E:\Steam_Machine_Learning\Game_data\3_build_recommendation_system.py

# Bước 6: Chạy file 4_web_app.py (Khởi động trang Web lên trình duyệt)
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m streamlit run E:\Steam_Machine_Learning\Game_data\4_web_app.py
```

### 1.4. Trọn bộ câu lệnh CMD chạy từ A đến Z (Dùng khi mang sang máy tính khác)

```cmd
# Bước 1: Di chuyển vào thư mục chứa dự án (thay đường dẫn tùy theo máy)
cd duong_dan_toi_thu_muc\Game_data

# Bước 2: Nâng cấp công cụ cài đặt pip
python -m pip install --upgrade pip

# Bước 3: Cài đặt toàn bộ 10 thư viện cần thiết
pip install pandas numpy scikit-learn scipy joblib requests streamlit openpyxl matplotlib seaborn

# Bước 4: Chạy file 1_price_prediction_pipeline.py
python 1_price_prediction_pipeline.py

# Bước 5: Chạy file 3_build_recommendation_system.py
python 3_build_recommendation_system.py

# Bước 6: Chạy file 4_web_app.py
python -m streamlit run 4_web_app.py
```

---

## PHẦN 2: MÔ TẢ DỰ ÁN & BẢNG GIẢI THÍCH ĐẦY ĐỦ CÁC TỪ VIẾT TẮT

### 2.1. Mô tả chi tiết Dự án
* **Tên dự án:** Ứng dụng Cửa hàng Game thông minh: Dự báo giá & Gợi ý game cá nhân hóa (GAMESTORE AI).
* **Nền tảng hỗ trợ:**
  1. **Steam PC:** Cửa hàng game trên máy vi tính cá nhân.
  2. **Nintendo Switch eShop:** Cửa hàng game trên máy chơi game Nintendo Switch.
* **Dữ liệu đầu vào:**
  * Đọc 100% từ các file CSV (Comma-Separated Values — Tệp dữ liệu bảng mở bằng Excel).
  * Lưu trữ tại thư mục: `E:\Steam_Machine_Learning\Game_data\data\cleaned_verified\`
* **Mô hình Dự báo giá trong 3 tháng tới (Price Prediction):**
  * Cho 3 mô hình Machine Learning (Học máy) thi đấu (Tournament):
    1. **Random Forest:** Thuật toán Rừng ngẫu nhiên.
    2. **Gradient Boosting:** Thuật toán Tăng cường độ dốc.
    3. **Ridge Regression:** Thuật toán Hồi quy tuyến tính Ridge.
* **Hệ thống Gợi ý game lai ghép (Hybrid Recommendation System):**
  * Kết hợp 3 cấu trúc thuật toán:
    1. **SVD (Singular Value Decomposition):** Phân rã giá trị suy biến / Lọc cộng tác.
    2. **TF-IDF (Term Frequency-Inverse Document Frequency):** Lọc theo nội dung thể loại.
    3. **KNN (K-Nearest Neighbors):** Thuật toán tìm $K$ láng giềng gần nhất.

### 2.2. Bảng giải thích toàn bộ Ký hiệu & Từ viết tắt (Glossary)

#### A. Thuật ngữ Hệ thống & Máy tính
* **AI (Artificial Intelligence):** Trí tuệ nhân tạo.
* **ML (Machine Learning):** Học máy — Máy tính tự học quy luật từ dữ liệu.
* **CSV (Comma-Separated Values):** Tệp bảng dữ liệu phân cách bằng dấu phẩy, mở bằng Excel.
* **CMD (Command Prompt):** Cửa sổ dòng lệnh màu đen của hệ điều hành Windows.
* **PC (Personal Computer):** Máy vi tính cá nhân.
* **UI (User Interface):** Giao diện người dùng trên trang Web.
* **URL (Uniform Resource Locator):** Đường dẫn / Địa chỉ trang Web.

#### B. Thuật ngữ Game & Cửa hàng
* **AppID (Application Identification):** Mã số định danh duy nhất của từng tựa game.
* **User:** Người dùng / Người chơi game (Game thủ).
* **CCU (Concurrent Users):** Số lượng người đang chơi game trực tuyến cùng một lúc.
* **1h:** 1 giờ qua (Số người chơi tính trong 1 tiếng gần nhất).
* **24h:** 24 giờ qua (Đỉnh số người chơi cao nhất trong vòng 1 ngày qua).
* **3T:** 3 Tháng tới (Khoảng thời gian AI dự đoán giá game trong tương lai).
* **F2P (Free-to-Play):** Game miễn phí 100%, giá bán $= \$0.00$.
* **Sale:** Đợt giảm giá / Chương trình khuyến mãi.
* **RPG (Role-Playing Game):** Thể loại game nhập vai.
* **FPS (First-Person Shooter):** Thể loại game bắn súng góc nhìn thứ nhất.

#### C. Thuật ngữ Thuật toán & Chỉ số đánh giá Mô hình
* **RF (Random Forest):** Mô hình Rừng ngẫu nhiên.
* **SVD (Singular Value Decomposition):** Ma trận phân rã tương tác giữa Người dùng và Game.
* **TF-IDF (Term Frequency-Inverse Document Frequency):** Đánh giá mức độ tương đồng về thể loại.
* **KNN (K-Nearest Neighbors):** Tìm kiếm các tựa game có chỉ số gần giống nhau nhất.
* **MAE (Mean Absolute Error):** Sai số tuyệt đối trung bình — Chỉ số này càng nhỏ càng tốt.
* **RMSE (Root Mean Square Error):** Căn bậc hai sai số bình phương trung bình — Càng nhỏ càng tốt.
* **R2 ($R^2$ / R-Squared / Hệ số xác định):** Độ chính xác của mô hình, càng gần $1.0$ là càng chính xác.

---

## PHẦN 3: CẤU TRÚC THƯ MỤC CHI TIẾT CỦA DỰ ÁN

```text
E:\Steam_Machine_Learning\Game_data\
├── 1_price_prediction_pipeline.py    # [FILE CHẠY SỐ 1] Huấn luyện 3 mô hình dự báo giá 3 tháng tới
├── 3_build_recommendation_system.py  # [FILE CHẠY SỐ 2] Huấn luyện 3 cấu trúc gợi ý & đồng bộ User
├── 4_web_app.py                      # [FILE CHẠY SỐ 3] Chạy giao diện trang Web (Streamlit)
├── HUONG_DAN_SU_DUNG.txt             # File tài liệu hướng dẫn sử dụng từ A đến Z
├── requirements.txt                  # File liệt kê danh sách 10 thư viện cần cài đặt
│
└── data\
    └── cleaned_verified\             # Thư mục chứa toàn bộ các file dữ liệu CSV
        ├── steam_users_profile_verified.csv        # Bảng 1: Hồ sơ người dùng Steam
        ├── steam_user_owned_games_verified.csv     # Bảng 2: Kho game người dùng đang sở hữu
        ├── master_price_predicted.csv              # Bảng 3: Giá hiện tại & giá dự báo 3 tháng tới
        ├── ml_price_tournament_leaderboard.csv     # Bảng 4: Bảng xếp hạng 3 mô hình dự báo giá
        ├── master_recommendations_ready.csv        # Bảng 5: Dữ liệu tổng hợp phục vụ trang Web
        ├── user_personalized_recommendations.csv   # Bảng 6: Danh sách gợi ý riêng cho từng User
        └── ml_recommendation_structures_report.csv # Bảng 7: Báo cáo kết quả 3 cấu trúc gợi ý
```

---

## PHẦN 4: HƯỚNG DẪN CHI TIẾT TỪNG BƯỚC CÀI ĐẶT & CHẠY TỪNG FILE BẰNG CMD

### BƯỚC 0: MỞ CỬA SỔ CMD VÀ CÀI ĐẶT 10 THƯ VIỆN (CHỈ CẦN LÀM 1 LẦN ĐẦU TIÊN)

#### 1. Cách mở cửa sổ CMD (Command Prompt)
* Nhấn tổ hợp phím `Windows + R` trên bàn phím.
* Gõ chữ: `cmd` $\rightarrow$ Nhấn phím `Enter` (Cửa sổ màu đen hiện ra).

#### 2. Câu lệnh di chuyển vào thư mục dự án
```cmd
E:
cd E:\Steam_Machine_Learning\Game_data
```

#### 3. Câu lệnh cài gộp tất cả 10 thư viện trong 1 lần chạy
* **Trên máy tính gốc của ADMIN:**
  ```cmd
  C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install pandas numpy scikit-learn scipy joblib requests streamlit openpyxl matplotlib seaborn
  ```
* **Trên máy tính khác:**
  ```cmd
  pip install pandas numpy scikit-learn scipy joblib requests streamlit openpyxl matplotlib seaborn
  ```

#### 4. Câu lệnh cài lẻ từng thư viện (Nếu máy báo thiếu thư viện nào thì copy dòng đó)
1. **Thư viện `pandas`** (Đọc và xử lý file CSV):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install pandas`
   * Máy khác: `pip install pandas`
2. **Thư viện `numpy`** (Tính toán ma trận số học):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install numpy`
   * Máy khác: `pip install numpy`
3. **Thư viện `scikit-learn`** (Chứa các mô hình Học máy):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install scikit-learn`
   * Máy khác: `pip install scikit-learn`
4. **Thư viện `scipy`** (Tính toán ma trận thưa cho hệ gợi ý):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install scipy`
   * Máy khác: `pip install scipy`
5. **Thư viện `joblib`** (Lưu trữ mô hình AI đã huấn luyện):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install joblib`
   * Máy khác: `pip install joblib`
6. **Thư viện `requests`** (Kết nối đường dẫn Store):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install requests`
   * Máy khác: `pip install requests`
7. **Thư viện `streamlit`** (Chạy giao diện trang Web):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install streamlit`
   * Máy khác: `pip install streamlit`
8. **Thư viện `openpyxl`** (Đọc/ghi file Excel `.xlsx`):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install openpyxl`
   * Máy khác: `pip install openpyxl`
9. **Thư viện `matplotlib`** (Vẽ biểu đồ thống kê):
   * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install matplotlib`
   * Máy khác: `pip install matplotlib`
10. **Thư viện `seaborn`** (Vẽ biểu đồ phân tích nâng cao):
    * Máy ADMIN: `C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install seaborn`
    * Máy khác: `pip install seaborn`

#### 5. Câu lệnh kiểm tra xem 10 thư viện đã cài thành công chưa
```cmd
C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -c "import pandas, numpy, sklearn, scipy, joblib, requests, streamlit, openpyxl, matplotlib, seaborn; print('CAI DAT THANH CONG 100%!')"
```

---

### BƯỚC 1: CHẠY FILE SỐ 1 $\rightarrow$ `1_price_prediction_pipeline.py`
* **Tên file cần chạy:** `1_price_prediction_pipeline.py`
* **Câu lệnh CMD để chạy trên máy của ADMIN:**
  ```cmd
  C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe 1_price_prediction_pipeline.py
  ```
* **Câu lệnh CMD để chạy trên máy khác:**
  ```cmd
  python 1_price_prediction_pipeline.py
  ```
* **Nhiệm vụ của file này:**
  * Đọc dữ liệu danh sách game, giá hiện tại, phần trăm giảm giá, đáy lịch sử, điểm đánh giá, CCU.
  * Huấn luyện 3 mô hình Học máy (`Random Forest`, `Gradient Boosting`, `Ridge Regression`) để dự đoán mức giá của từng tựa game trong 3 tháng tới.
  * Đánh giá sai số (`MAE`, `RMSE`, `R2`) và gắn nhãn khuyến nghị: `"NEN MUA NGAY"` hoặc `"CHO DOT SALE"`.
* **File kết quả sinh ra sau khi chạy xong:**
  1. `data\cleaned_verified\master_price_predicted.csv`
  2. `data\cleaned_verified\ml_price_tournament_leaderboard.csv`

---

### BƯỚC 2: CHẠY FILE SỐ 2 $\rightarrow$ `3_build_recommendation_system.py`
* **Tên file cần chạy:** `3_build_recommendation_system.py`
* **Câu lệnh CMD để chạy trên máy của ADMIN:**
  ```cmd
  C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe 3_build_recommendation_system.py
  ```
* **Câu lệnh CMD để chạy trên máy khác:**
  ```cmd
  python 3_build_recommendation_system.py
  ```
* **File đầu vào nó đọc (Inputs):**
  1. `data\cleaned_verified\master_price_predicted.csv`
  2. `data\cleaned_verified\steam_users_profile_verified.csv`
  3. `data\cleaned_verified\steam_user_owned_games_verified.csv`
* **Nhiệm vụ của file này:**
  * Đọc hồ sơ của từng người dùng và danh sách các game mà người đó đang sở hữu.
  * Loại trừ 100% các game đã mua khỏi danh sách gợi ý.
  * Chạy 3 cấu trúc Học máy (`SVD` + `TF-IDF` + `KNN`) để tính điểm `"Độ Hợp Gu (%)"` cho từng tựa game.
* **File kết quả sinh ra sau khi chạy xong (Outputs):**
  1. `data\cleaned_verified\master_recommendations_ready.csv`
  2. `data\cleaned_verified\user_personalized_recommendations.csv`
  3. `data\cleaned_verified\ml_recommendation_structures_report.csv`

---

### BƯỚC 3: CHẠY FILE SỐ 3 $\rightarrow$ `4_web_app.py` (MỞ GIAO DIỆN TRANG WEB)
* **Tên file cần chạy:** `4_web_app.py`
* **Câu lệnh CMD để chạy trên máy của ADMIN:**
  ```cmd
  C:\Users\ADMIN\AppData\Local\Python\pythoncore-3.14-64\python.exe -m streamlit run 4_web_app.py
  ```
* **Câu lệnh CMD để chạy trên máy khác:**
  ```cmd
  python -m streamlit run 4_web_app.py
  ```
* **Cách mở trang Web:**
  * Sau khi bấm `Enter` 3 giây, trình duyệt Web sẽ tự động bật lên địa chỉ: `http://localhost:8501`
  * *(Cách mở nhanh trong PyCharm: Mở file `4_web_app.py` và nhấn tổ hợp phím `Shift + F10`)*.
  * **Lưu ý quan trọng:** Nếu lần đầu chạy Streamlit mà CMD hỏi `"Email:"`, chỉ cần bấm phím `ENTER` để bỏ qua.

---

## PHẦN 5: HƯỚNG DẪN SỬ DỤNG 5 TRANG CHỨC NĂNG TRÊN WEB APP (DASHBOARD)

### A. Cột Bộ Lọc Bên Trái Màn Hình (Sidebar)
* **👤 Game Thủ:** Chọn hồ sơ người dùng từ file CSV (Bảng kho game và danh sách gợi ý sẽ đổi theo).
* **💎 Chế độ Cửa hàng:** Bấm chọn xem game `"Trả Phí"` ($> \$0$), `"Tất Cả"` hoặc `"Miễn Phí"` ($\$0$).
* **💰 Trần ngân sách ($):** Kéo thanh trượt để lọc các game có giá rẻ hơn mức ngân sách.
* **🖥️ Nền tảng:** Bấm chọn `"Mọi Hệ"`, chỉ xem game `"Steam"` (PC) hoặc chỉ xem game `"Switch"` (Nintendo).
* **🔄 Đồng Bộ Lại CSV:** Bấm nút này để Web tự động chạy lại File 3 (`3_build_recommendation_system.py`) và cập nhật dữ liệu CSV mới nhất.

### B. 5 Trang Chính Trên Màn Hình (5 Tabs)

#### 1. Tab `🎮 Cửa Hàng Gợi Ý`
* Hiển thị trực tiếp **"Bảng Game Hiện Tại Đang Sở Hữu"** của người dùng đang chọn.
* Hiển thị danh sách game AI đề xuất mua (đã loại trừ 100% các game trong bảng sở hữu).
* Trên mỗi thẻ game hiển thị rõ **3 cột giá**:
  * **Cột 1 (Giá Hiện Tại / Giá Sale):** Giá đang bán kèm Giá gốc và % giảm giá.
  * **Cột 2 (Dự Báo 3T Tới):** Giá dự đoán trong 3 tháng tới (`"↑ Hết sale"` hoặc `"↓ Chờ sale"`).
  * **Cột 3 (Đáy Lịch Sử):** Mức giá thấp nhất lịch sử của tựa game đó.
* Có **2 nút bấm** trên mỗi thẻ game:
  1. Nút mở thẳng trang sản phẩm trên **Steam Store / Nintendo eShop**.
  2. Nút xem chi tiết điểm số AI (`SVD`, `TF-IDF`, `KNN`) kèm lượng người chơi `CCU`.

#### 2. Tab `📦 Kho Game Đang Sở Hữu`
* Xem bảng chi tiết toàn bộ kho game của người dùng và biểu đồ cột so sánh số giờ chơi.

#### 3. Tab `🔥 Xếp Hạng CCU`
* Biểu đồ và danh sách Top 10 tựa game có số người đang chơi cùng lúc (`CCU 1h` và `Đỉnh 24h`) cao nhất.

#### 4. Tab `🏷️ Săn Sale & Giá 3T`
* Ô tìm kiếm tên game bất kỳ và bộ lọc nhanh các game `"🟢 Mua Ngay"` hoặc `"🔥 Đang Sale"`.

#### 5. Tab `📊 Bảng CSV & Mô Hình`
* Xem bảng xếp hạng 3 mô hình Dự Báo Giá, báo cáo 3 cấu trúc Học Máy Gợi Ý và xem trực tiếp nội dung các file CSV ngay trên Web.

---

## PHẦN 6: CÁCH XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING PLAYBOOK)

| Mã lỗi / Hiện tượng | Nguyên nhân | Cách khắc phục chuẩn xác |
| :--- | :--- | :--- |
| **1. Lỗi `ModuleNotFoundError: No module named '...'`** | Môi trường Python chưa cài đủ thư viện. | Copy và chạy lại câu lệnh cài đặt 10 thư viện ở **PHẦN 1 (Bước 3)** hoặc **PHẦN 4 (Bước 0)**. |
| **2. Chạy Streamlit lần đầu bị đứng im ở chữ `"Email:"` trong CMD** | Streamlit yêu cầu đăng ký email nhận thông báo ở lần chạy đầu tiên. | Bấm phím `ENTER` trên bàn phím (để trống không cần nhập gì), Web sẽ tự mở lên ngay. |
| **3. Trên Web báo `"Chưa tìm thấy đủ file CSV trong data/cleaned_verified/"`** | Chưa chạy các file pipeline tạo dữ liệu đầu ra hoặc thiếu file CSV. | Bấm nút `"🔄 Đồng Bộ & Huấn Luyện Từ File CSV"` trên màn hình Web, hoặc chạy lại file `1_price_prediction_pipeline.py` và `3_build_recommendation_system.py`. |
| **4. Sửa code trong PyCharm nhưng giao diện Web chưa thay đổi** | File chưa được lưu hoặc trình duyệt chưa làm mới lại trang. | Bấm `Ctrl + S` trong PyCharm để lưu code, sau đó sang trình duyệt Web bấm phím `R` (hoặc `F5`). |
| **5. Muốn tắt hẳn trang Web đang chạy** | Server Streamlit vẫn đang chạy ngầm trong cửa sổ dòng lệnh. | Bấm chuột vào cửa sổ CMD/Terminal đang chạy và nhấn tổ hợp phím: `Ctrl + C`. |

---

## PHẦN 7: DỮ LIỆU MẪU HUẤN LUYỆN AI / AGENT (INSTRUCTION - RESPONSE PAIRS)
*(Phần này giúp các AI Agent học nhanh cách phản hồi khi người dùng truy vấn về dự án GAMESTORE AI)*

### Mẫu 1: Hỏi về thứ tự chạy dự án
* **User Prompt:** "Tôi mới tải source code dự án GameStore AI về, tôi cần chạy những file nào và theo thứ tự ra sao?"
* **Agent Response:**
  Bạn cần chạy lần lượt **3 file Python** theo đúng thứ tự bắt buộc sau:
  1. `1_price_prediction_pipeline.py` (Huấn luyện AI dự báo giá game trong 3 tháng tới — sinh ra `master_price_predicted.csv` và `ml_price_tournament_leaderboard.csv`).
  2. `3_build_recommendation_system.py` (Huấn luyện hệ gợi ý game cho từng User — sinh ra `master_recommendations_ready.csv`, `user_personalized_recommendations.csv`, và `ml_recommendation_structures_report.csv`).
  3. `4_web_app.py` (Khởi chạy giao diện Web bằng lệnh `python -m streamlit run 4_web_app.py` tại địa chỉ `http://localhost:8501`).

### Mẫu 2: Hỏi về thuật toán AI được sử dụng
* **User Prompt:** "Dự án GameStore AI dùng những thuật toán Machine Learning nào?"
* **Agent Response:**
  Dự án sử dụng 2 cụm mô hình Machine Learning chính:
  1. **Mô hình Dự báo giá 3 tháng tới (Price Prediction Tournament):** Cho 3 thuật toán thi đấu gồm **Random Forest** (Rừng ngẫu nhiên), **Gradient Boosting** (Tăng cường độ dốc) và **Ridge Regression** (Hồi quy tuyến tính Ridge), được đánh giá qua các chỉ số `MAE`, `RMSE` và $R^2$.
  2. **Hệ thống Gợi ý game lai ghép (Hybrid Recommendation System):** Kết hợp 3 cấu trúc gồm **SVD** (Phân rã giá trị suy biến / Lọc cộng tác), **TF-IDF** (Lọc theo nội dung thể loại) và **KNN** ($K$ láng giềng gần nhất) để tính điểm `"Độ Hợp Gu (%)"` và loại trừ 100% các game người dùng đã sở hữu.

### Mẫu 3: Xử lý lỗi treo CMD khi chạy Web
* **User Prompt:** "Tại sao tôi gõ lệnh chạy `4_web_app.py` xong màn hình CMD cứ đứng im ở dòng chữ `Email:` mà không mở web?"
* **Agent Response:**
  Đây là thông báo mặc định của thư viện Streamlit trong lần đầu tiên khởi chạy. Bạn **không cần nhập gì cả**, chỉ cần click vào cửa sổ CMD và nhấn phím **ENTER** trên bàn phím, trình duyệt sẽ tự động mở trang Web tại địa chỉ `http://localhost:8501`.