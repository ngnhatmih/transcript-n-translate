"""Đơn vị của trường `vram` trong `GET /api/status` — dữ liệu của MIỀN.

Vì sao nằm ở `domain/` chứ không ở `api/` hay `adapters/`: cùng một hằng được
đọc ở hai tầng — route (`app/api/routes_registry.py`, nơi trả JSON) và adapter
(`app/adapters/gpu.py`, nơi cầm số của `nvidia-smi`) — mà `app/api` **không được**
import `app/adapters` (`tests/test_api_sources.py::test_api_layer_does_not_import_adapters`).
Miền là tầng duy nhất cả hai được phép đọc, và đơn vị thì đúng là dữ liệu miền:
"MБ" không phải chi tiết của HTTP lẫn chi tiết của driver card.

Giao diện KHÔNG tự thêm đơn vị: `screens/OllamaDown.tsx` in đúng chuỗi backend nói
(`VRAM: 1467 MiB`), vì một con số trần trụi (`3200`) không nói được gì.
"""

#: Đơn vị của `vram` trong `/api/status` và của `nvidia-smi --query-gpu=memory.used`.
VRAM_UNIT = "MiB"
