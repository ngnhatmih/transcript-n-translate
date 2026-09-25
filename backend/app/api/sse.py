"""Một SSE stream toàn cục cho mọi job.

Vì sao toàn cục chứ không phải mỗi job một stream: giao diện hiển thị cả hàng
đợi, nên nó cần biết mọi job đổi trạng thái. Mỗi job một kết nối sẽ mở hàng
chục kết nối và mỗi cái lại phải polling.

THỨ TỰ là hợp đồng, không phải chi tiết cài đặt: kết nối ĐĂNG KÝ trước rồi mới
chụp ảnh trạng thái (`snapshot`). Làm ngược lại — chụp trước, nghe sau — thì
một chuyển trạng thái rơi đúng vào cửa sổ giữa hai bước sẽ mất VĨNH VIỄN: không
sự kiện nào tới, và cũng không có gì chụp lại. Nghe trước thì cửa sổ đó biến
mất: sự kiện rơi vào giữa được xếp vào hàng đợi và gửi ngay sau ảnh chụp. Vì
cùng một chuyển có thể vừa nằm trong ảnh chụp vừa nằm trong hàng đợi, phần gửi
khử trùng theo NỘI DUNG: một sự kiện trùng với ảnh chụp bị bỏ qua — và chỉ bỏ
qua một lần, nên không có chuyển nào vừa bị mất vừa bị gửi hai lần.

Khi cửa sổ đó chứa NHIỀU chuyển của CÙNG một job, hàng đợi phải được thu về
bản MỚI NHẤT mỗi job trước khi gửi: khử trùng một-một sẽ bỏ bản mới (trùng ảnh
chụp) rồi phát lại bản CŨ ngay sau ảnh chụp, và client đứng ở trạng thái cũ —
kể cả `done` — mà không còn sự kiện nào sửa lại. Thu về bản mới nhất giống đúng
cách hàng đợi giới hạn đã chọn cho subscriber chậm, và làm phần phát lại sau
ảnh chụp đơn điệu theo thời gian.

CHỜ SỰ KIỆN TRÊN EVENT LOOP, không trong một luồng: `stream_events` là async
generator nên Starlette `async for` thẳng nó. Bản sync generator trước đây bị
Starlette bọc trong `iterate_in_threadpool`, và mỗi `next()` đang chờ sự kiện
giữ một trong 40 token mặc định của anyio suốt vòng đời kết nối — 40 subscriber
là mọi route sync xếp hàng sau họ.

`JobEventBroker` là hàng đợi TRONG BỘ NHỚ, không bền: sự kiện chỉ có nghĩa với
client đang mở stream. Nguồn sự thật vẫn là bảng `jobs`, và ảnh chụp đầu stream
gửi lại trạng thái hiện tại của mọi job — nên client chỉ cần MỘT kết nối này.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator, Callable


class _Subscriber:
    """Một kết nối SSE đang mở: hàng đợi asyncio GIỚI HẠN + loop của nó.

    `publish` chạy trên LUỒNG worker còn hàng đợi thuộc event loop, nên
    `call_soon_threadsafe` là đường DUY NHẤT được phép chạm vào hàng đợi.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, max_queue: int) -> None:
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self.closed = False

    def offer(self, event: dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            self.loop.call_soon_threadsafe(self._offer_now, event)
        except RuntimeError:  # loop đã đóng: client đã ngắt
            self.closed = True

    def _offer_now(self, event: dict[str, Any]) -> None:
        # Chạy TRÊN loop nên `get_nowait`/`put_nowait` không thể chặn ai.
        if self.queue.full():
            try:
                self.queue.get_nowait()      # bỏ sự kiện CŨ NHẤT, giữ cái mới
            except asyncio.QueueEmpty:
                pass
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def wait(self, heartbeat: float) -> dict[str, Any] | None:
        """Sự kiện kế tiếp, hoặc `None` nếu hết một nhịp tim.

        Chờ TRÊN event loop: không token threadpool nào bị giữ trong lúc này.
        """
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=heartbeat)
        except asyncio.TimeoutError:
            return None


class JobEventBroker:
    """Phát sự kiện job tới mọi subscriber, không cho subscriber chậm giữ bộ nhớ.

    Mỗi subscriber một hàng đợi GIỚI HẠN (`max_queue`): đầy thì bỏ sự kiện CŨ
    NHẤT để lấy chỗ cho sự kiện mới. Giữ cái cũ là sai hướng — giao diện đang
    xem tiến độ hiện tại, một sự kiện `queued` từ ba phút trước vô dụng hơn
    `progress = 0.9` vừa publish.
    """

    def __init__(self, *, max_queue: int = 500) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[_Subscriber] = []
        self._max_queue = max_queue

    def subscribe(self) -> _Subscriber:
        """Đăng ký một kết nối, gắn vào event loop ĐANG chạy."""
        sub = _Subscriber(asyncio.get_running_loop(), self._max_queue)
        with self._lock:
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)
        # Đánh dấu đóng luôn: một `publish` đang bay tới sau khi loop đóng
        # không được ném RuntimeError vào luồng worker.
        sub.closed = True

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            sub.offer(event)                 # không chặn luồng worker


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_events(broker: JobEventBroker, *, heartbeat: float = 15.0,
                        snapshot: Callable[[], list[dict[str, Any]]] | None = None
                        ) -> AsyncIterator[str]:
    """Generator của một kết nối SSE.

    `heartbeat` không phải trang trí: proxy và trình duyệt cắt kết nối im lặng
    sau ~60s không có byte nào, và hàng đợi có thể im lâu hơn thế. Comment
    `: heartbeat` giữ kết nối sống mà client không hiểu thành sự kiện.

    `snapshot` được gọi SAU khi đã subscribe (xem thứ tự ở docstring đầu tệp):
    đó là toàn bộ lý do nó là một callable chứ không phải danh sách dựng sẵn ở
    route.
    """
    sub = broker.subscribe()
    try:
        yield ": connected\n\n"
        pending: dict[Any, dict[str, Any]] = {}
        if snapshot is not None:
            # Đọc DB là I/O ĐỒNG BỘ mà generator này chạy thẳng trên event loop,
            # nên đẩy sang executor: chặn loop là chặn cả server.
            events = await asyncio.get_running_loop().run_in_executor(None, snapshot)
            for event in events:
                yield format_sse(event)
                pending[event.get("id")] = event
            # Sự kiện publish trong cửa sổ "subscribe -> ảnh chụp" nằm sẵn trong
            # hàng đợi dưới dạng callback `call_soon_threadsafe` chưa chạy. Nhường
            # loop một nhịp để chúng vào hàng đợi TRƯỚC khi lọc: bỏ qua bước này
            # thì bản CŨ có thể tới sau ảnh chụp.
            await asyncio.sleep(0)
            newest: dict[Any, dict[str, Any]] = {}
            while not sub.queue.empty():
                # Chỉ những gì ĐÃ có sẵn; vòng lặp chính vẫn chờ bình thường.
                queued = sub.queue.get_nowait()
                newest[queued.get("id")] = queued
            for job_id, event in newest.items():
                if pending.get(job_id) == event:
                    # Ảnh chụp đã gửi đúng chuyển này rồi: bỏ bản trong hàng đợi.
                    del pending[job_id]
                    continue
                pending.pop(job_id, None)
                yield format_sse(event)
        while True:
            event = await sub.wait(heartbeat)
            if event is None:
                yield ": heartbeat\n\n"
                continue
            if pending.get(event.get("id")) == event:
                # Ảnh chụp đã gửi đúng chuyển này rồi: bỏ bản trong hàng đợi.
                del pending[event.get("id")]
                continue
            yield format_sse(event)
    finally:
        broker.unsubscribe(sub)
