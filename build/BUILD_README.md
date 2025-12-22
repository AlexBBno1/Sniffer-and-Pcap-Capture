# 🛠️ WiFi Sniffer Control Panel - Build System

本資料夾包含將 WiFi Sniffer 打包成專業 Windows 應用程式所需的所有工具。

---

## 📋 快速開始

### 一鍵構建

```
雙擊 build.bat
```

這將自動：
1. ✅ 檢查 Python 環境
2. ✅ 安裝所有依賴套件
3. ✅ 生成應用程式圖示
4. ✅ 使用 PyInstaller 打包成 EXE
5. ✅ 如有安裝 Inno Setup，自動建立安裝程式

---

## 📁 資料夾結構

```
build/
├── wifi_sniffer_app.py      # 增強版主程式（含系統匣）
├── wifi_sniffer.spec        # PyInstaller 配置檔
├── requirements_build.txt   # 構建所需的套件
├── create_icon.py           # 圖示生成器
│
├── build.bat                # 🔥 一鍵構建腳本
├── run_dev.bat              # 開發模式運行
├── clean.bat                # 清理構建檔案
│
├── assets/                  # 資源檔案
│   ├── icon.ico            # 應用程式圖示
│   ├── icon.png            # PNG 版本圖示
│   └── version_info.txt    # EXE 版本資訊
│
├── installer/               # 安裝程式相關
│   └── setup.iss           # Inno Setup 腳本
│
├── dist/                    # [構建後產生]
│   └── WiFi_Sniffer_Control_Panel.exe
│
└── output/                  # [構建後產生]
    └── WiFi_Sniffer_Setup_v2.0.exe
```

---

## 🔧 構建步驟詳解

### 步驟 1：安裝依賴

```powershell
pip install -r requirements_build.txt
```

包含：
- `flask` - Web 框架
- `paramiko` - SSH 連線
- `pystray` - 系統匣圖示
- `pillow` - 圖像處理
- `pyinstaller` - EXE 打包

### 步驟 2：生成圖示

```powershell
python create_icon.py
```

生成 `assets/icon.ico` 和 `assets/icon.png`

### 步驟 3：打包 EXE

```powershell
pyinstaller wifi_sniffer.spec
```

輸出到 `dist/WiFi_Sniffer_Control_Panel.exe`

### 步驟 4：建立安裝程式（可選）

需要先安裝 [Inno Setup 6](https://jrsoftware.org/isdl.php)

```powershell
# 使用 Inno Setup 編譯器打開
installer\setup.iss
```

或命令列：
```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
```

---

## 🖥️ 應用程式功能

### 系統匣圖示

打包後的應用程式會在系統匣顯示圖示：

- **左鍵雙擊**：打開網頁控制面板
- **右鍵選單**：
  - 🌐 Open Web Panel - 打開瀏覽器
  - 📁 Open Downloads - 打開下載資料夾
  - ℹ️ Status - 顯示狀態
  - ❌ Exit - 結束程式

### 圖示顏色

| 顏色 | 狀態 |
|------|------|
| 🟢 綠色 | 正常運行，無擷取 |
| 🟡 黃色 | 正在擷取封包 |
| 🔴 紅色 | 連線錯誤 |

---

## 📦 分發方式

### 方式 1：直接分發 EXE

把 `dist/WiFi_Sniffer_Control_Panel.exe` 複製到目標電腦即可使用。

**優點**：簡單快速
**缺點**：沒有開始選單/桌面捷徑

### 方式 2：使用安裝程式

把 `output/WiFi_Sniffer_Setup_v2.0.exe` 發給使用者。

**優點**：
- 專業的安裝精靈介面
- 自動建立桌面捷徑
- 自動建立開始選單項目
- 可選開機自動啟動
- 完整的解除安裝支援

---

## ❓ 常見問題

### Q: PyInstaller 構建失敗？

**A:** 常見原因：
1. 防毒軟體阻擋 - 暫時關閉或加入白名單
2. 路徑包含中文 - 嘗試移動到英文路徑
3. 依賴缺失 - 執行 `pip install -r requirements_build.txt`

### Q: EXE 啟動很慢？

**A:** 這是正常的。PyInstaller 打包的 EXE 在首次啟動時需要解壓縮依賴，大約需要 3-5 秒。

### Q: 系統匣圖示沒出現？

**A:** 確保已安裝 `pystray` 和 `pillow`：
```powershell
pip install pystray pillow
```

### Q: 如何自訂圖示？

**A:** 編輯 `create_icon.py` 中的顏色和形狀，或直接替換 `assets/icon.ico`。

### Q: 安裝程式語言？

**A:** 安裝程式支援多國語言（英文、簡體中文、繁體中文、日文），會自動根據 Windows 語言選擇。

---

## 🔄 版本資訊

- **構建版本**：2.0.0
- **Python 版本**：3.8+
- **PyInstaller**：6.0+
- **Inno Setup**：6.x

---

## 📞 技術支援

如遇到構建問題，請提供：
- Python 版本：`python --version`
- pip list：`pip list`
- 完整的錯誤訊息


