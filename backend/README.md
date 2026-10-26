# Comment Collector — Backend (YouTube only)

## 1. Cài đặt

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Cấu hình key

```bash
cp .env.example .env
# mở .env, dán key YouTube Data API v3 vào YOUTUBE_API_KEY
```

Bật API tại: <https://console.cloud.google.com/apis/library/youtube.googleapis.com>

## 3. Chạy

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: <http://localhost:8000/docs>

## 4. Test bằng curl

```bash
curl -X POST http://localhost:8000/api/collect \
  -H "Content-Type: application/json" \
  -d '{
    "group": "1",
    "platform": "youtube",
    "source": "review điện thoại",
    "dateRange": { "from": "2020-01-01", "to": "2025-01-01" },
    "abbreviations": ["ngta","mn","cx","k","ko","dc","j","z","ns"],
    "matchMode": "word",
    "limit": 50,
    "sort": "newest",
    "options": {
      "includeReplies": true,
      "removeDuplicates": true,
      "skipLinks": true
    }
  }'
```

`source` chấp nhận được:

| Kiểu             | Ví dụ                                              |
| ---------------- | -------------------------------------------------- |
| Video URL / ID   | `https://youtube.com/watch?v=dQw4w9WgXcQ`           |
| Kênh URL         | `https://youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw` |
| Handle           | `@sontungmtp`                                      |
| Keyword          | `review điện thoại`, `#shopee`, …                  |

## 5. Nối frontend

Trong `frontend/index.html`, thay `generateMock()` bằng:

```js
const res  = await fetch('http://localhost:8000/api/collect', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(configObject()),
});
const data = await res.json();
state.results = data.results;
renderResults();
```

## 6. Quỹ đạo mở rộng sau này

Khi thêm Facebook/TikTok/Shopee/Threads:
- thêm `services/facebook.py`, `services/tiktok.py`, …
- trong `main.py`, thay block `if req.platform != "youtube"` bằng dispatcher `PLATFORM_HANDLERS[req.platform]`
- mỗi service chỉ cần cùng contract: `async def collect(req) -> dict`
```

---

### Sau khi chạy

```bash
# Kiểm tra server
curl http://localhost:8000/api/health
# → {"status":"ok","youtube_configured":true}