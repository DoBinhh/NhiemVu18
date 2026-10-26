"""
YouTube Data API v3 client cho Comment Collector.
Chỉ mở endpoint:
  - search.list          (tìm video theo keyword / kênh)
  - commentThreads.list  (lấy bình luận + replies)
  - videos.list          (metadata video)
  - channels.list        (đổi @handle -> channelId)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.schemas import CollectRequest
from app.services.text_filter import build_regex, find_words, has_link

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Số video tối đa sẽ quét mỗi lần thu thập (mỗi video tốn ~N units cho comment).
MAX_VIDEOS_PER_RUN = 20
# Số trang comment tối đa mỗi video.
MAX_COMMENT_PAGES_PER_VIDEO = 3
# Số trang replies mỗi thread — commentThreads đã trả sẵn reply tối đa, không cần riêng.
COMMENT_PAGE_SIZE = 100

# Regex nhận diện input người dùng nhập ở ô "source"
_VIDEO_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*?v=|shorts/)|youtu\.be/)([\w-]{11})"
)
_VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")
_CHANNEL_URL_RE = re.compile(r"youtube\.com/channel/(UC[\w-]{22})")
_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
_HANDLE_RE = re.compile(r"(?:youtube\.com/)?@([\w.-]+)")


class YouTubeError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class YouTubeClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise YouTubeError("Thiếu YOUTUBE_API_KEY", 500)
        self.api_key = api_key
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ #
    #  Low level
    # ------------------------------------------------------------------ #
    async def _get(self, path: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        r = await self._http.get(f"{YOUTUBE_API_BASE}{path}", params=params)
        if r.status_code != 200:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") or r.text
            except Exception:
                msg = r.text
            raise YouTubeError(f"YouTube API {r.status_code}: {msg}", 502)
        return r.json()

    # ------------------------------------------------------------------ #
    #  Endpoints
    # ------------------------------------------------------------------ #
    async def resolve_channel_id(self, handle: str) -> Optional[str]:
        """Đổi @handle -> channelId. Trả None nếu không tìm thấy."""
        try:
            data = await self._get(
                "/channels", {"part": "id", "forHandle": handle.lstrip("@")}
            )
        except YouTubeError:
            return None
        items = data.get("items", [])
        return items[0]["id"] if items else None

    async def search_videos(
        self,
        *,
        keyword: Optional[str] = None,
        channel_id: Optional[str] = None,
        published_after: str,
        published_before: str,
        max_results: int = MAX_VIDEOS_PER_RUN,
    ) -> list[str]:
        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "date",
            "publishedAfter": published_after,
            "publishedBefore": published_before,
        }
        if channel_id:
            params["channelId"] = channel_id
        if keyword:
            params["q"] = keyword

        data = await self._get("/search", params)
        return [
            item["id"]["videoId"]
            for item in data.get("items", [])
            if item.get("id", {}).get("videoId")
        ]

    async def get_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        if not video_ids:
            return {}
        data = await self._get(
            "/videos",
            {"part": "snippet,statistics", "id": ",".join(video_ids[:50])},
        )
        return {v["id"]: v for v in data.get("items", [])}

    async def get_comments(
        self, video_id: str, *, max_pages: int = MAX_COMMENT_PAGES_PER_VIDEO
    ) -> list[dict]:
        """Lấy top-level comments (kèm replies nếu có). Không phân biệt thời gian."""
        out: list[dict] = []
        page_token: Optional[str] = None

        for _ in range(max_pages):
            params = {
                "part": "snippet,replies",
                "videoId": video_id,
                "maxResults": COMMENT_PAGE_SIZE,
                "order": "time",
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._get("/commentThreads", params)

            for thread in data.get("items", []):
                sn = thread["snippet"]["topLevelComment"]["snippet"]
                tid = thread["snippet"]["topLevelComment"]["id"]
                replies = []
                for rep in thread.get("replies", {}).get("comments", []):
                    rs = rep["snippet"]
                    replies.append(
                        {
                            "id": rep["id"],
                            "author": rs.get("authorDisplayName", ""),
                            "text": rs.get("textDisplay") or rs.get("textOriginal", ""),
                            "likes": int(rs.get("likeCount", 0)),
                            "publishedAt": rs.get("publishedAt"),
                        }
                    )
                out.append(
                    {
                        "id": tid,
                        "author": sn.get("authorDisplayName", ""),
                        "text": sn.get("textDisplay") or sn.get("textOriginal", ""),
                        "likes": int(sn.get("likeCount", 0)),
                        "publishedAt": sn.get("publishedAt"),
                        "replies": replies,
                    }
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return out

    # ------------------------------------------------------------------ #
    #  High level collect
    # ------------------------------------------------------------------ #
    async def _resolve_video_ids(self, source: str, after: str, before: str) -> list[str]:
        """Từ ô 'source' tự nhận dạng: video URL, channel URL/ID, @handle, hay keyword."""
        source = (source or "").strip()
        if not source:
            raise YouTubeError("Bạn chưa nhập nguồn dữ liệu", 400)

        # 1) Video cụ thể
        m = _VIDEO_URL_RE.search(source)
        if m:
            return [m.group(1)]
        if _VIDEO_ID_RE.fullmatch(source):
            return [source]

        # 2) Kênh cụ thể
        m = _CHANNEL_URL_RE.search(source)
        if m:
            return await self.search_videos(
                channel_id=m.group(1), published_after=after, published_before=before
            )
        if _CHANNEL_ID_RE.fullmatch(source):
            return await self.search_videos(
                channel_id=source, published_after=after, published_before=before
            )

        # @handle -> channelId
        hm = _HANDLE_RE.search(source)
        if hm:
            cid = await self.resolve_channel_id(hm.group(1))
            if cid:
                return await self.search_videos(
                    channel_id=cid, published_after=after, published_before=before
                )

        # 3) Keyword (mặc định)
        return await self.search_videos(
            keyword=source, published_after=after, published_before=before
        )

    async def collect(self, req: CollectRequest) -> dict:
        regex = build_regex(req.abbreviations, req.matchMode)
        if regex is None:
            raise YouTubeError("Danh sách từ viết tắt đang rỗng", 400)

        # Chuẩn hoá khoảng thời gian
        try:
            from_dt = datetime.fromisoformat(req.dateRange.from_date).replace(
                tzinfo=timezone.utc
            )
            to_dt = datetime.fromisoformat(req.dateRange.to).replace(
                tzinfo=timezone.utc
            ) + (
                # nếu client gửi dạng YYYY-MM-DD, đẩy mốc cuối về cuối ngày
                timezone.utc.utcoffset(None) or _offset_for_ymd(req.dateRange.to)
            )
        except ValueError:
            raise YouTubeError("Định dạng dateRange không hợp lệ", 400)

        after = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        before = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Tìm video
        video_ids = await self._resolve_video_ids(req.source, after, before)
        if not video_ids:
            return self._empty(req, 0)

        video_details = await self.get_video_details(video_ids)

        seen_texts: set[str] = set()
        results: list[dict] = []

        for vid in video_ids:
            try:
                comments = await self.get_comments(vid)
            except YouTubeError:
                # bình luận bị tắt / video bị gỡ nhưng vẫn hiện trong search
                continue

            for c in comments:
                candidates = [c]
                if req.options.includeReplies:
                    candidates.extend(c.get("replies", []))

                for cm in candidates:
                    text = cm.get("text") or ""
                    if req.options.skipLinks and has_link(text):
                        continue

                    words = find_words(text, regex)
                    if not words:
                        continue

                    if req.options.removeDuplicates:
                        key = text.strip().lower()
                        if key in seen_texts:
                            continue
                        seen_texts.add(key)

                    published = cm.get("publishedAt") or ""
                    if published:
                        try:
                            cdt = datetime.fromisoformat(
                                published.replace("Z", "+00:00")
                            )
                            if cdt < from_dt or cdt > to_dt:
                                continue
                        except ValueError:
                            pass

                    meta = video_details.get(vid, {}).get("snippet", {})
                    results.append(
                        {
                            "id": cm["id"],
                            "author": cm.get("author", ""),
                            "text": text,
                            "likes": cm.get("likes", 0),
                            "publishedAt": published,
                            "matched": words,
                            "platform": "youtube",
                            "video": {
                                "id": vid,
                                "title": meta.get("title", ""),
                                "url": f"https://www.youtube.com/watch?v={vid}",
                            },
                        }
                    )

            # dừng sớm nếu đã dư
            if len(results) >= req.limit * 2:
                break

        # Sắp xếp
        if req.sort == "newest":
            results.sort(key=lambda c: c["publishedAt"] or "", reverse=True)
        elif req.sort == "oldest":
            results.sort(key=lambda c: c["publishedAt"] or "")
        else:  # likes
            results.sort(key=lambda c: c["likes"], reverse=True)

        results = results[: req.limit]

        return {
            "platform": "youtube",
            "group": req.group,
            "source": req.source,
            "dateRange": {"from": req.dateRange.from_date, "to": req.dateRange.to},
            "videosScanned": len(video_ids),
            "total": len(results),
            "stats": {
                "matched": len(results),
                "uniqueWords": len({w for c in results for w in c["matched"]}),
                "uniqueAuthors": len({c["author"] for c in results}),
            },
            "results": results,
        }

    @staticmethod
    def _empty(req: CollectRequest, videos_scanned: int) -> dict:
        return {
            "platform": "youtube",
            "group": req.group,
            "source": req.source,
            "dateRange": {"from": req.dateRange.from_date, "to": req.dateRange.to},
            "videosScanned": videos_scanned,
            "total": 0,
            "stats": {"matched": 0, "uniqueWords": 0, "uniqueAuthors": 0},
            "results": [],
        }


def _offset_for_ymd(value: str):
    """Nếu value dạng YYYY-MM-DD (không có giờ), cộng 23h59m để lấy hết ngày."""
    from datetime import timedelta

    if len(value) == 10:
        return timedelta(hours=23, minutes=59, seconds=59)
    return timedelta(0)