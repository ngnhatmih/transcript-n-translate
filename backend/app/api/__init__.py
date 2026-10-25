"""Tầng HTTP của phu-de-lab.

`create_app()` nằm ở `app.api.app`; các route chia theo tài nguyên. `app/api`
KHÔNG import adapter — mọi thứ nó cần được `app/main.py` đặt vào `app.state`,
nên test dựng app được mà không cần ffmpeg, model hay GPU.
"""
