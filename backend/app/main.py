"""FastAPI entrypoint — chỉ mở YouTube, các nền tảng khác trả 400."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas import CollectRequest
from app.services.youtube import YouTubeClient, YouTubeError

app = FastAPI(
    title="Comment Collector API",
    version="0.1.0",
    description="Thu thập bình luận chứa từ viết tắt. Hiện chỉ hỗ trợ YouTube.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "name": "Comment Collector API",
        "version": "0.1.0",
        "supported_platforms": ["youtube"],
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "youtube_configured": bool(settings.youtube_api_key),
    }


@app.post("/api/collect")
async def collect(req: CollectRequest) -> dict:
    if req.platform != "youtube":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nền tảng '{req.platform}' chưa mở. "
                "Hiện tại chỉ hỗ trợ 'youtube'."
            ),
        )

    if not settings.youtube_api_key:
        raise HTTPException(
            status_code=500,
            detail="Chưa cấu hình YOUTUBE_API_KEY trong file backend/.env",
        )

    client = YouTubeClient(settings.youtube_api_key)
    try:
        return await client.collect(req)
    except YouTubeError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    finally:
        await client.close()