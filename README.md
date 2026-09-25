# 台灣科技職缺雷達

每天自動彙整台灣與國外的科技職缺，放在 GitHub Pages 上，可依技能、地區、年資、類別等條件篩選；點選職缺後，會用你自己的資料產生一份貼近該職缺的履歷。整套服務免費，不需要任何 LLM API token。

## 架構

```
GitHub Actions（每天 06:00 台灣時間）
  └─ scraper/（Python）抓各來源 → 正規化（技能 / 年資 / 地區 / 類別）→ 與昨天資料合併、去重
       ├─ site/data/jobs.json、desc/*.json、meta.json → 部署到 GitHub Pages（網站只讀這些靜態檔）
       └─ Supabase（選用）保存歷史資料與每日統計
GitHub Pages（docs/）
  ├─ 篩選、搜尋、收藏（localStorage）
  └─ 履歷生成：瀏覽器端關鍵字與技能比對；可選用開源多語言嵌入模型做語意排序（Transformers.js，在瀏覽器執行）
```

### 為什麼網站不直接讀 Supabase？
Supabase 免費版限制 500 MB 資料庫與每月流量上限。網站讀的是 Pages 上的靜態 JSON（有 CDN），訪客再多也不會用到 Supabase 的額度，Supabase 只在每天的 Action 裡寫入一次，同時也避免免費專案因閒置 7 天被暫停。資料超過 60 天沒再出現會自動刪除，實際用量大約只有幾十 MB。

## 資料來源

| 來源 | 區域 | 方式 |
|---|---|---|
| 台灣就業通 | 台灣 | 勞動部開放資料（data.gov.tw #44062），取最近更新約 1,000 筆中的科技職缺 |
| 104 人力銀行 | 台灣 | **預設停用**：GitHub Actions 的雲端 IP 會被回 403 |
| Yourator | 台灣 | **預設停用**：同上 |
| Cake | 台灣 | **預設停用**：同上 |
| Remotive | 國外遠端 | 官方公開 API |
| RemoteOK | 國外遠端 | 官方公開 API |
| Arbeitnow | 歐洲 | 官方公開 API |
| Himalayas | 國外遠端 | 官方公開 API |
| HN Who's Hiring | 國外 | Algolia HN API |

LinkedIn、Indeed、Glassdoor 的使用條款禁止爬取，也沒有免費的職缺 API，所以不直接抓取。網站側邊欄會提供「到這些網站搜尋同樣關鍵字」的連結。

爬蟲每天只跑一次，每個請求之間有間隔，並設有數量上限，每筆職缺都會連回原始頁面。若任一網站的條款改變，把 `sources.json` 裡該來源改成 `"enabled": false` 即可停用。某個來源當天抓取失敗時，會暫時沿用前一天的資料（最多 14 天），頁面底部會顯示各來源的狀態。

## 設定步驟

1. **開啟 GitHub Pages**：Repo → Settings → Pages → Source 選 **GitHub Actions**。
2. **（選用）Supabase**
   1. 到 https://supabase.com 建立免費專案。
   2. 在 SQL Editor 執行 `supabase/schema.sql`。
   3. Repo → Settings → Secrets and variables → Actions，新增：
      - `SUPABASE_URL`：例如 `https://xxxx.supabase.co`
      - `SUPABASE_SERVICE_KEY`：Project Settings → API 的 `service_role` key（只放在 Secrets，不要放進前端）
3. **第一次執行**：Actions → *Update jobs & deploy site* → Run workflow。之後每天自動更新；只修改前端並 push 時，會直接重新部署，不會重抓。

## 本機開發

```bash
pip install -r requirements-dev.txt
python -m pytest -q                 # Python 測試
npm test                            # 履歷生成邏輯測試（Node 18+）
python scripts/make_sample_data.py  # 產生範例資料
python -m http.server -d docs 8000  # 打開 http://localhost:8000
python -m scraper.main --only remotive hn --out docs/data   # 實際抓部分來源
```

## 履歷生成怎麼運作

1. 在「我的資料」填寫基本資料、技能、經歷（每段多寫幾點）、專案與學歷。資料只存在瀏覽器的 localStorage，可以匯出成 JSON 備份。
2. 選擇職缺後按「產生這份職缺的優化履歷」：
   - 從職缺內容抽出技能，與你的技能及經歷比對，計算符合度；
   - 依相關度排序經歷條列與專案，並從摘要中挑出最相關的句子，套入中文或英文的摘要模板；
   - 職缺相關的技能會以粗體標示，也會列出職缺要求但你資料裡沒提到的技能，供你自行補充。
3. 想要更精準時，可以按「語意比對」：瀏覽器會下載開源的 `paraphrase-multilingual-MiniLM-L12-v2`（約 120 MB，只下載一次），在本機計算語意相似度，不會呼叫任何 API。
4. 履歷可以直接在畫面上編輯，再下載 PDF（使用瀏覽器列印）或複製成 Markdown。

系統只會挑選、排序、強調你自己寫的內容，不會捏造經歷。

## 調整

- 技能字典：`scraper/skills.py`，前端會自動使用同一份字典。
- 職務類別與地區規則：`scraper/normalize.py`
- 各來源的抓取數量與開關：`sources.json`
- 更新時間：`.github/workflows/update-jobs.yml` 的 `cron`
