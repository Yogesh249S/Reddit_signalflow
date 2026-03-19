import asyncio
import logging
import os
import time
from typing import AsyncIterator

import aiohttp
from ingestion.base import BaseIngester

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Default tech channels — override with YOUTUBE_CHANNELS env var
DEFAULT_CHANNELS = [
    "UCsBjURrPoezykLs9EqgamOA",  # Fireship
    "UCVhQ2NnY5Rskt6UjCUkJ_DA",  # Tech with Tim
    "UCWX3yG9WUQQ4pFMxfDSEBOQ",  # ThePrimeagen
    "UCXuqSBlHAE6Xw-yeJA0Tunw",  # Linus Tech Tips
    "UC295-Dw4tztFUTpCHoEjVAQ",  # The Coding Train
    "UCnUYZLuoy1rq1aVMwx4aTzw",  # Google for Developers
    "UCddiUEpeqJcYeBxX1IVBKvQ",  # Theo
    "UCwFl9Y49sWChrddETD9QhZA",  # ByteByteGo (correct ID)
]


class YouTubeIngester(BaseIngester):
    source_name   = "youtube"
    kafka_topic   = "youtube.comments.raw"
    poll_interval = 21600.0  # 6 hours — quota-conscious

    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self.session = None
        self._seen_videos:   set[str] = set()
        self._seen_comments: set[str] = set()
        # Cache channel_id -> uploads_playlist_id so we only fetch it once
        self._uploads_playlist_cache: dict[str, str] = {}

        channels_env = os.environ.get("YOUTUBE_CHANNELS", "")
        self.channels = (
            [c.strip() for c in channels_env.split(",") if c.strip()]
            if channels_env else DEFAULT_CHANNELS
        )

    async def setup(self) -> None:
        if not self.api_key:
            raise RuntimeError("YOUTUBE_API_KEY environment variable not set.")
        self.session = aiohttp.ClientSession()
        logger.info("YouTube ingester ready — tracking %d channels.", len(self.channels))

    async def poll(self) -> AsyncIterator[dict]:
        for channel_id in self.channels:
            async for comment in self._fetch_channel_comments(channel_id):
                yield comment
            await asyncio.sleep(0.5)

    async def _get_uploads_playlist_id(self, channel_id: str) -> str | None:
        """
        Get the uploads playlist ID for a channel.
        Cost: 1 unit (replaces the 100-unit search call).
        Result is cached — only called once per channel per process lifetime.
        """
        if channel_id in self._uploads_playlist_cache:
            return self._uploads_playlist_cache[channel_id]

        params = {
            "key":  self.api_key,
            "id":   channel_id,
            "part": "contentDetails",
        }
        async with self.session.get(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "API error"))
            items = data.get("items", [])
            if not items:
                logger.warning("No channel found for ID %s", channel_id)
                return None
            playlist_id = (
                items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if playlist_id:
                self._uploads_playlist_cache[channel_id] = playlist_id
            return playlist_id

    async def _get_latest_videos(self, channel_id: str, max_results: int = 3) -> list:
        """
        Fetch most recent videos via uploads playlist.
        Cost: 1 unit per call (was 100 units with /search).
        """
        playlist_id = await self._get_uploads_playlist_id(channel_id)
        if not playlist_id:
            return []

        params = {
            "key":        self.api_key,
            "playlistId": playlist_id,
            "part":       "snippet",
            "maxResults": max_results,
        }
        async with self.session.get(
            f"{YOUTUBE_API_BASE}/playlistItems",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "API error"))

            videos = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId")
                if not video_id:
                    continue
                # Reshape to match the format _fetch_channel_comments expects
                videos.append({
                    "id":      {"videoId": video_id},
                    "snippet": {
                        "title":        snippet.get("title", ""),
                        "channelTitle": snippet.get("channelTitle", ""),
                    },
                })
            return videos

    async def _fetch_channel_comments(self, channel_id: str) -> AsyncIterator[dict]:
        """Fetch latest videos from a channel then pull comments for each."""
        try:
            videos = await self._get_latest_videos(channel_id, max_results=3)
        except Exception as e:
            logger.warning("Failed to fetch videos for channel %s: %s", channel_id, e)
            return

        for video in videos:
            video_id      = video["id"]["videoId"]
            video_title   = video["snippet"]["title"]
            channel_title = video["snippet"]["channelTitle"]

            async for comment in self._fetch_video_comments(
                video_id, video_title, channel_id, channel_title
            ):
                yield comment

            await asyncio.sleep(0.2)

    async def _fetch_video_comments(
        self,
        video_id: str,
        video_title: str,
        channel_id: str,
        channel_title: str,
        max_pages: int = 2,
    ) -> AsyncIterator[dict]:
        """
        Fetch top-level comment threads for a video.
        Cost: 1 unit per page, 100 comments per page.
        """
        page_token    = None
        pages_fetched = 0

        while pages_fetched < max_pages:
            params = {
                "key":        self.api_key,
                "videoId":    video_id,
                "part":       "id,snippet",
                "order":      "relevance",
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                async with self.session.get(
                    f"{YOUTUBE_API_BASE}/commentThreads",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()

                    if "error" in data:
                        err = data["error"].get("message", "")
                        if "commentsDisabled" in err or "disabled comments" in err:
                            logger.debug("Comments disabled for video %s", video_id)
                        elif "quota" in err.lower():
                            logger.warning("YouTube quota exhausted — halting poll cycle")
                            return
                        else:
                            logger.warning("YouTube API error for %s: %s", video_id, err)
                        return

                    for item in data.get("items", []):
                        comment_id = item.get("id", "")
                        if comment_id in self._seen_comments:
                            continue
                        self._seen_comments.add(comment_id)

                        if len(self._seen_comments) > 50_000:
                            self._seen_comments = set(list(self._seen_comments)[25_000:])

                        item["video_title"]   = video_title
                        item["channel_id"]    = channel_id
                        item["channel_title"] = channel_title
                        yield item

                    page_token = data.get("nextPageToken")
                    pages_fetched += 1
                    if not page_token:
                        break

            except aiohttp.ClientError as e:
                logger.warning("YouTube request error for %s: %s", video_id, e)
                break

    async def teardown(self) -> None:
        if self.session:
            await self.session.close()
