# 鐘點站名錶價格監控

部署來源：https://github.com/hourstack2020-ctrl/watch-monitor
網站：https://hourstack-watch-monitor.onrender.com

## 功能與使用
- 三站公開商品列表：永生、玩錶舍、名錶雷達站。
- 密碼保護、搜尋、品牌／來源／錶況篩選、排序、每頁 100 筆分頁、CSV 匯出（全部篩選結果）。
- 查看歷史價格：首次取得數字價格及每次價格變更時新增紀錄；歷史從首次爬取起算。
- 變動標記：新上架、漲價、降價、資料變更、重新上架、無變動、疑似下架。
- 疑似下架：僅在該站沒有錯誤、分頁掃描完畢，且連續兩輪未見時標記。
- 立即更新：已登入管理員可在網站按鈕啟動，資料庫鎖避免並行爬取。
- 每站最多 200 頁、頁間隔 2 秒；達頁數上限或零商品會回報不完整，不會誤報成功。
- 商品年份依刊登內容解析，通常是保卡／保單年；缺值不猜測。
- 同型號可能不同年份與錶況，不代表同一商品。

## 已建立的部署資源
- Render Web Service：hourstack-watch-monitor（Singapore、免費方案）。閒置後首次開啟可能需約一分鐘。
- Supabase：watch-monitor（Tokyo）。watches、history、crawl_runs 三張資料表均啟用 RLS；anon/authenticated 不可存取。
- 後端專用 watch_monitor_app 角色僅可讀寫監控資料，不使用資料庫管理員帳號。
- 排程設定：UTC 00:00、12:00，即台灣 08:00、20:00。
- Render Cron：hourstack-watch-crawler 已啟用（Singapore、Starter），台灣時間每天 08:00、20:00 執行；每月最低 US$1。

## 環境變數（僅設定於 Render，勿提交秘密）
- DATABASE_URL：Supabase Session Pooler URI，專用角色，SSL 必須啟用。
- ADMIN_PASSWORD：獨立管理員密碼（登入帳號可用 admin）。
- SKIP_DB_INIT=1：現有資料表已透過 Supabase migration 建立，專用角色不進行建表。
- MAX_PAGES_PER_SITE=200
- CRAWL_DELAY_SECONDS=2
- PYTHON_VERSION=3.12.10

## 驗證與維護
- /health：程序存活。
- /ready：資料庫連線與商品資料表可讀性。
- /api/watches、/api/history?url=...、/api/status：均需管理員認證。
- POST /api/crawl：需管理員認證及 X-Watch-Monitor: 1，自動於背景啟動爬取。
- 新帳戶重新部署時，請先建立資料表及專用角色／權限，再啟動 Render。render.yaml 不會替外部 Supabase 建表。
- 目前以公開 Git URL 部署；尚未連接 Git provider credentials 時，推送後需在 Render 選擇部署最新版本。部署中應避免啟動人工更新。
- 站點改版、存取限制與分頁變化可能造成缺漏；不要繞過驗證碼或存取限制。
