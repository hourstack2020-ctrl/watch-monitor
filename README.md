# 鐘點站名錶價格監控

部署來源：https://github.com/hourstack2020-ctrl/watch-monitor
網站：https://hourstack-watch-monitor.onrender.com

## 功能與使用
- 四站公開商品列表：鐘點站、永生、玩錶舍、名錶雷達站。
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
- Supabase：watch-monitor（Tokyo）。watches、history、crawl_runs、removal_events 四張資料表均啟用 RLS；anon/authenticated 不可存取。
- 後端專用 watch_monitor_app 角色僅可讀寫監控資料，不使用資料庫管理員帳號。
- 正式排程：`0 3-11 * * *`（UTC），台灣每天 11:00、12:00、13:00、14:00、15:00、16:00、17:00、18:00、19:00，共 9 次。
- Render Cron：hourstack-watch-crawler 已啟用（Singapore、Starter），每月最低 US$1。已於 2026-10-17 在 Render 後台儲存並透過服務 API 確認正式排程為 `0 3-11 * * *`，與 render.yaml 一致；台灣每天 11:00～19:00 每整點執行。

## 環境變數（僅設定於 Render，勿提交秘密）
- DATABASE_URL：Supabase Session Pooler URI，專用角色，SSL 必須啟用。
- ADMIN_PASSWORD：獨立管理員密碼（登入帳號為 HS，區分大小寫）。
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

## 低於鐘點站售價清單
- 相同品牌完整型號、明確面盤顏色、保卡／保單年份與錶帶／帶身款式比對；四項任一不明者排除。新舊等級不限制，雙方資料分別顯示。大小寫及型號分隔符號正規化；Omega 點號與連續數字、Panerai 前導零採一致表示。
- 相同條件多筆鐘點站商品時，採最低數字刊登價；僅列出嚴格低於該價格的同業商品。
- 暫未見於最新列表、疑似下架、洽詢價或無法可靠辨識型號者不參與比價。
- 清單顯示雙方圖片、售價、年份、錶況、資料時間、商品連結、價差及百分比，可搜尋及按來源篩選。
- 五株與三板等帶身分開；皮帶、膠帶、織物帶須明確相同顏色與材質。帶長、鍊節數與配件仍需核對原商品。
- GET /api/comparisons 需管理員認證；每次排程一併更新四站資料。

## 每日下架紀錄
- GET /api/removals?date=YYYY-MM-DD 需管理員認證；預設台灣今天，以 Asia/Taipei 00:00 至次日 00:00 歸日。
- 四家店分組，顯示下架判定時商品快照、最後售價、圖片、最後看見與判定時間；可選日期查閱。
- 只有該站完整成功爬取且連續兩輪未見，才在第二輪建立一次疑似下架事件。失敗或分頁不完整不累加。
- 紀錄保留；商品重新出現時顯示已重新出現，再度下架可建立新事件。判定時間非實際下架時間，也不代表成交。
- 紀錄從功能啟用後開始；既有疑似下架資料缺少可靠判定時間，不倒填事件。

## 商品列表預設排序
- 原站順序・變價優先：數字價格實際變動者依最近變價時間置頂，其餘按店家及原網站商品出現順序排列。
- 新商品首次價格不視為變價；單純重新爬取不更新變價時間。已知變價時間由既有價格歷史回填。
- 只有完整成功掃描該站全部分頁才更新其原站順序，部分失敗保留先前完整順序。
- 價格高低、型號及最近爬取仍可手動切換；匯出 CSV 沿用目前篩選與排序。

## 每月上架／下架頁籤
- /api/monthly-events?month=YYYY-MM：管理員認證；台灣時間每月起訖邊界，按四店分組，保留各次事件。
- 上架事件 listing_events 儲存商品快照；新上架 listed、重新上架 returned、首次建檔 initial 分開計數。下架沿用 removal_events。
- 既有庫存一律回填 initial，不宣稱是真正當月新上架；回填的商品資料／價格是現有值，畫面明確註明。啟用後才開始觀測新上架及重新上架事件。
- 首次完整掃描完成前的庫存只列首次建檔，不列新上架；商品持續存在不重複建立事件。每次重新上架保留獨立快照。
- 預設本月，可選月份、店家、事件類別、搜尋型號；每店先顯示 20 筆，可繼續載入，支援手機卡片。
- 記錄時間為系統偵測時間，非店家實際上架／下架時間；系統啟用前紀錄無法回溯。計數為事件筆數。

## 保留商品變更標記
- 每輪無新變更時保留既有新上架、漲價、降價、資料變更或重新上架標記，不重設為無變動。
- 真正再次變價、資料修改或重新上架時，改顯示最近一次實際變更；疑似下架仍按原規則判定。
- 價格歷史保留所有已記錄的價格；舊版已覆蓋成無變動的漲跌標記，可依最近一次數字價格變化恢復。無可靠歷史者不猜測。

## iPhone 主畫面網頁 App
- Safari 開啟正式網站並登入 → 分享 → 加入主畫面 → 打開為網頁 App（如有顯示）→ 加入。
- 加入 HS 圖示、manifest standalone、apple-touch-icon、iPhone 安全邊界與安裝引導；沿用網站帳密和雲端資料。非 App Store 原生 App。
- /manifest.webmanifest、/app-icon-180.png、/app-icon-192.png、/app-icon-512.png、/service-worker.js 僅含公開安裝資產。
- Service Worker 只快取公開圖示；HTML 和 API 不快取，驗證頁及 API 回應設定 private, no-store。離線顯示重新連線提示，不提供離線庫存。
- 首次由主畫面開啟可能需要重新登入。尚未透過實體 iPhone 驗證安裝流程；伺服器與安裝資產、登入保護及離線邏輯已驗證。

## 手機低價推播通知
- 由 iPhone 主畫面 App 點「啟用低價通知」並允許；可測試或關閉此裝置通知。瀏覽器與手機系統權限須由使用者親自操作。
- 完整成功爬取四站後，依同型號、面盤顏色、保卡年份、錶帶規則檢查。首次符合、離開清單後再次符合、或同商品再次降價才通知；新舊程度不限制。
- 每支訂閱裝置獨立去重；多筆符合時合併為一則通知，附部分商品與價差，點擊進入比價清單。無法保證店家改價當下即時通知。
- push_subscriptions、push_alert_state 啟用 RLS、禁止 anon/authenticated，僅後端專用角色存取。過期 404/410 訂閱自動清理。
- Render Web 與 Cron 都需 VAPID_PUBLIC_KEY、VAPID_PRIVATE_KEY、VAPID_SUBJECT；私鑰僅存在環境設定，不可提交 Git。
- /api/push/config 需認證；POST /api/push/subscribe、unsubscribe、test 需認證及 X-Watch-Monitor: 1。僅允許已知 Apple/Google/Mozilla HTTPS 推播端點。
- 已驗證訂閱、去重邏輯、權限與 API；實體 iPhone 是否收到通知需使用者授權後按「測試通知」確認。

## iPhone App 內登入
- 首頁未登入時顯示手機適配的帳密表單，不依賴 iOS 主畫面 App 的 HTTP Basic 登入提示。
- /api/login 驗證原有 HS 帳號與 ADMIN_PASSWORD，建立 30 天簽章工作階段；Secure、HttpOnly、SameSite=Lax cookie，換密碼即失效。
- SESSION_SECRET 為 Render Web 專用的隨機簽章密鑰，不可提交 Git。原有 Basic 認證保留供維運 API 使用。
- 未登入 API 回傳 401 JSON，不再觸發系統 Basic 對話框。商品資料與登入頁均不快取。
