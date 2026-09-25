"""Một SSE stream toàn cục cho mọi job.

Vì sao toàn cục chứ không phải mỗi job một stream: giao diện hiển thị cả hàng
đợi, nên nó cần biết mọi job đổi trạng thái. Mỗi job một kết nối sẽ mở hàng
chục kết nối và mỗi cái lại phải polling.

`JobEventBroker` là hàng đợi TRONG BỘ NHỚ, không bền: sự kiện chỉ có nghĩa với
client đang mở stream. Nguồn sự thật vẫn là bảng `jobs`; client nối lại thì đọc
`GET /api/jobs` rồi mới nghe stream, nên mất một sự kiện không làm sai trạng thái.
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator


class JobEventBroker:
    """Phát sự kiện job tới mọi subscriber, không cho subscriber chậm giữ bộ nhớ.

    Mỗi subscriber một `queue.Queue` GIỚI HẠN (`max_queue`): đầy thì bỏ sự kiện
    CŨ NHẤT để lấy chỗ cho sự kiện mới. Giữ cái cũ là sai hướng — giao diện đang
    xem tiến độ hiện tại, một sự kiện `queued` từ ba phút trước vô dụng hơn
    `progress = 0.9` vừa publish.
    """

    def __init__(self, *, max_queue: int = 500) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._max_queue = max_queue

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            if q.full():
                try:
                    q.get_nowait()          # bỏ sự kiện CŨ NHẤT, giữ cái mới
                except queue.Empty:
                    pass
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def stream_events(broker: JobEventBroker, *, heartbeat: float = 15.0) -> Iterator[str]:
    """Generator của một kết nối SSE.

    `heartbeat` không phải trang trí: proxy và trình duyệt cắt kết nối im lặng
    sau ~60s không có byte nào, và hàng đợi có thể im lâu hơn thế. Comment
    `: heartbeat` giữ kết nối sống mà client không hiểu thành sự kiện.
    """
    q = broker.subscribe()
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = q.get(timeout=heartbeat)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield format_sse(event)
    finally:
        broker.unsubscribe(q)
