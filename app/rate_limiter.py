"""CP3 — Rate limiting bằng thuật toán sliding window.

Đếm số request trong 60 giây **gần nhất** (cửa sổ trượt), thay vì đếm theo
phút đồng hồ. Đếm theo phút đồng hồ có lỗ hổng: 10 request lúc 10:00:59 và
10 request lúc 10:01:01 = 20 request trong 2 giây mà vẫn "đúng luật".

Cấu trúc dữ liệu: Redis Sorted Set (ZSET), score = timestamp của request.
"""

from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, status

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, client, limit_per_minute: int) -> None:
        self.client = client
        self.limit = limit_per_minute

    @staticmethod
    def _key(user_id: str) -> str:
        """CHO SẴN — mỗi user một key riêng."""
        return f"ratelimit:{user_id}"

    def hit_count(self, user_id: str, now: float | None = None) -> int:
        """Số request của user trong ``WINDOW_SECONDS`` giây gần nhất."""
        now = now if now is not None else time.time()
        key = self._key(user_id)
        # Xóa các entry cũ hơn cửa sổ 60 giây
        self.client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
        return self.client.zcard(key)

    def check(self, user_id: str, now: float | None = None) -> None:
        """Cho qua nếu còn quota, ngược lại raise 429.

        Thứ tự: **kiểm tra trước, ghi nhận sau**. Ghi trước rồi đếm sẽ chặn
        nhầm ngay ở request thứ ``limit``.
        Member phải DUY NHẤT để 2 request cùng timestamp không ghi đè nhau.
        """
        now = now if now is not None else time.time()
        key = self._key(user_id)
        count = self.hit_count(user_id, now)
        if count >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        # Ghi nhận request này với member duy nhất
        self.client.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        self.client.expire(key, WINDOW_SECONDS)
