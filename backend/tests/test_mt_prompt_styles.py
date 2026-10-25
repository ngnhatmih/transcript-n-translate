"""Hatch BIẾN THỂ PROMPT của lượt đo echo (`20261019-prompt-echo-sweep`).

Bốn biến thể V0–V3 là một phép ĐO, không phải một tính năng: chưa cái nào được
ship và mặc định vẫn là `hymt-json-p2` từng byte. Vì vậy tệp này kiểm đúng ba
thứ, theo đúng thứ tự nguy hiểm của chúng:

1. **Mặc định KHÔNG đổi** — ghim nguyên văn cả `system_prompt` lẫn `user_prompt`,
   cộng sha256 của cặp. Đây là bài quan trọng nhất: `system_prompt`/`user_prompt`
   dùng chung với `qwen2.5-3b`/`qwen2.5-7b`, nên một byte trôi ở đây là đổi prompt
   của hai engine đã có số ghim, trong khi phép đo chỉ nói về `hy-mt-1.5-7b`.
2. **Không rò rỉ sang engine khác** — biến môi trường của hatch đặt thành `v3`
   thì `qwen2.5-3b`/`opus-mt`/người gọi không truyền `engine_id` vẫn phải nhận
   ĐÚNG chuỗi ở (1). Hatch đọc biến môi trường SAU khi đã loại engine, nên tính
   chất này là code chứ không phải lời hứa.
3. **Mỗi biến thể có đúng tính chất định nghĩa nó** — V1 dời câu cấm xuống cuối
   (dời, không nhân bản), V2 thêm ĐÚNG một cặp input/output giữ số và không lấy
   chữ từ clip, V3 đánh số `[i]` từng dòng và giữ nguyên hợp đồng JSON.

Không model, không mạng: cả ba nhóm đều là phép so chuỗi.
"""
import hashlib

import pytest

from app.adapters.mt.prompts import (EXPERIMENT_PROMPT_ENGINE,
                                     EXPERIMENT_PROMPT_STYLE_ENV, PROMPT_STYLES,
                                     PROMPT_VERSION, STYLE_DEFAULT, STYLE_FEW_SHOT,
                                     STYLE_INSTRUCTION_LAST, STYLE_NUMBERED,
                                     experiment_prompt_style, system_prompt,
                                     user_prompt)
from app.domain.models import Segment, Term


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


#: Hai segment dùng cho MỌI phép so ở tệp này. Chữ Hán thật (lấy từ đầu clip
#: `20261019-name-patch-smoke`) vì biến thể nào cũng phải giữ nguyên khối dữ liệu
#: trừ phần được nó cố ý đổi.
BATCH = [seg(0, "作为一个搞艺术的"), seg(1, "赔了")]

#: `system_prompt([], target_lang="vi")` — ĐÚNG chuỗi `hymt-json-p2`/`qwen-json-p2`
#: đang ship (đoạn cuối là câu vá lỗi echo `p1` -> `p2`). Ghim nguyên văn chứ
#: không ghim một phần: một bài chỉ kiểm "có câu cấm chép" vẫn xanh khi ai đó đổi
#: thứ tự hoặc thêm dòng, mà đó lại đúng là thứ `PROMPT_VERSION` không được phép
#: bỏ sót.
DEFAULT_SYSTEM = "\n".join([
    "Bạn là dịch giả chuyên nghiệp sang vi.",
    "Dịch sát nghĩa, giữ nguyên văn phong và mức trang trọng của bản gốc.",
    "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác.",
    "TUYỆT ĐỐI không sao chép nguyên văn bản gốc: mỗi 'text' phải là câu vi, "
    "không được để lại chữ của bản gốc.",
])

#: `user_prompt(BATCH, source_lang="zh", target_lang="vi")` — cùng lý do trên.
#: Khối `Dữ liệu:` là `json.dumps(..., ensure_ascii=False)` của hai mục, nên nó
#: ghim luôn cả hình dạng payload mà `parse_batch_response` chờ.
DEFAULT_USER = "\n".join([
    "Dịch từng mục từ zh sang vi.",
    "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.",
    'Định dạng: {"translations": [{"i": <số>, "text": "<bản dịch>"}]}',
    'Dữ liệu: [{"i": 0, "text": "作为一个搞艺术的"}, {"i": 1, "text": "赔了"}]',
])

#: sha256 của `system_prompt + "\n@@\n" + user_prompt` (chính hai chuỗi trên).
#: Vì sao ghim CẢ hash khi đã ghim nguyên văn: hash bắt được thứ mắt người bỏ
#: qua — một khoảng trắng cuối dòng, một dấu tiếng Việt bị đổi tổ hợp — và nó là
#: con số duy nhất so được giữa hai lần chạy mà không phải đọc cả khối chữ.
DEFAULT_PAIR_SHA256 = (
    "765721f81e96a7a63fc017bf25da08d09f26513d9a3f20d21945d0946e875ab0")


def _pair(system: str, user: str) -> str:
    return f"{system}\n@@\n{user}"


def _default_pair() -> str:
    return _pair(system_prompt([], target_lang="vi"),
                 user_prompt(BATCH, source_lang="zh", target_lang="vi"))


# ---------------------------------------------------------------------------
# 1. MẶC ĐỊNH KHÔNG ĐỔI (byte-identical)
# ---------------------------------------------------------------------------

def test_the_default_system_prompt_is_byte_identical_to_the_shipped_one():
    assert system_prompt([], target_lang="vi") == DEFAULT_SYSTEM


def test_the_default_user_prompt_is_byte_identical_to_the_shipped_one():
    assert user_prompt(BATCH, source_lang="zh", target_lang="vi") == DEFAULT_USER


def test_the_default_prompt_pair_still_hashes_to_the_pinned_sha256():
    digest = hashlib.sha256(_default_pair().encode()).hexdigest()
    assert digest == DEFAULT_PAIR_SHA256, (
        "prompt mặc định đã đổi. `system_prompt`/`user_prompt` dùng chung với "
        "`qwen2.5-3b`/`qwen2.5-7b` — đổi ở đây là đổi prompt của hai engine đã "
        "có số ghim. Nếu thay đổi là CỐ Ý thì bump `PROMPT_VERSION` trước."
    )


def test_the_hy_mt_prompt_version_is_still_the_shipped_one():
    """Lượt đo KHÔNG được bump `PROMPT_VERSION` — chưa ship biến thể nào.

    Ghi một chuỗi mới vào đây là công bố một prompt đã ship; nhận một biến thể mà
    KHÔNG bump là đúng lỗi mà `PROMPT_VERSION` tồn tại để chặn. Nhãn của lượt đo
    nằm ở artifact (`prompt_style`), không ở cột này.
    """
    assert PROMPT_VERSION["hy-mt-1.5-7b"] == "hymt-json-p2"


# ---------------------------------------------------------------------------
# 2. KHÔNG RÒ RỈ SANG ENGINE KHÁC
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style", PROMPT_STYLES)
def test_engines_that_do_not_select_a_variant_get_the_default_text(monkeypatch,
                                                                   style):
    """Biến môi trường đặt thành `v3` thì `qwen2.5-3b` vẫn phải nhận `p2`.

    Đây là bài chống rò rỉ: `qwen2.5-3b` đi CÙNG `OllamaMtEngine.translate` với
    `hy-mt-1.5-7b`, nên nếu hatch đọc biến môi trường TRƯỚC khi xét `engine_id`
    thì một lượt đo `--styles v3` sẽ lặng lẽ dịch `qwen` bằng prompt khác — và số
    ghim của qwen (`p2`: 5/5, 0 echo) không còn nói về code đang chạy.
    """
    monkeypatch.setenv(EXPERIMENT_PROMPT_STYLE_ENV, style)
    for engine_id in ("qwen2.5-3b", "qwen2.5-7b", "opus-mt", None):
        assert system_prompt([], target_lang="vi", engine_id=engine_id) \
            == DEFAULT_SYSTEM, engine_id
        assert user_prompt(BATCH, source_lang="zh", target_lang="vi",
                           engine_id=engine_id) == DEFAULT_USER, engine_id


def test_the_experiment_engine_without_the_env_var_gets_the_default_text(monkeypatch):
    """Hatch TẮT (biến vắng mặt / rỗng) ⇒ chính engine được đo cũng chạy `p2`."""
    monkeypatch.delenv(EXPERIMENT_PROMPT_STYLE_ENV, raising=False)
    assert system_prompt([], target_lang="vi",
                         engine_id=EXPERIMENT_PROMPT_ENGINE) == DEFAULT_SYSTEM
    assert user_prompt(BATCH, source_lang="zh", target_lang="vi",
                       engine_id=EXPERIMENT_PROMPT_ENGINE) == DEFAULT_USER
    monkeypatch.setenv(EXPERIMENT_PROMPT_STYLE_ENV, "  ")
    assert experiment_prompt_style(EXPERIMENT_PROMPT_ENGINE) == STYLE_DEFAULT


@pytest.mark.parametrize("style", PROMPT_STYLES)
def test_the_hatch_returns_the_style_only_for_the_experiment_engine(monkeypatch,
                                                                    style):
    monkeypatch.setenv(EXPERIMENT_PROMPT_STYLE_ENV, style)
    assert experiment_prompt_style(EXPERIMENT_PROMPT_ENGINE) == style
    assert experiment_prompt_style("qwen2.5-3b") == STYLE_DEFAULT


def test_an_unknown_style_raises_instead_of_measuring_the_default(monkeypatch):
    """Gõ nhầm style phải NỔ, không được "đo" prompt mặc định dưới nhãn lạ.

    Một lượt đo sinh ra bốn artifact mà một cái mang nhãn `v03` nhưng chạy prompt
    mặc định là một bảng số SAI trong im lặng — đúng loại lỗi mà cả tệp này tồn
    tại để chặn.
    """
    monkeypatch.setenv(EXPERIMENT_PROMPT_STYLE_ENV, "v03")
    with pytest.raises(ValueError):
        experiment_prompt_style(EXPERIMENT_PROMPT_ENGINE)


# ---------------------------------------------------------------------------
# 3. MỖI BIẾN THỂ CÓ ĐÚNG TÍNH CHẤT ĐỊNH NGHĨA NÓ
# ---------------------------------------------------------------------------

def _prompts(monkeypatch, style: str, glossary: list[Term] | None = None):
    monkeypatch.setenv(EXPERIMENT_PROMPT_STYLE_ENV, style)
    system = system_prompt(glossary or [], target_lang="vi",
                           engine_id=EXPERIMENT_PROMPT_ENGINE)
    user = user_prompt(BATCH, source_lang="zh", target_lang="vi",
                       engine_id=EXPERIMENT_PROMPT_ENGINE)
    return system, user


def test_v1_moves_the_no_copy_rule_out_of_the_system_prompt(monkeypatch):
    system, _user = _prompts(monkeypatch, STYLE_INSTRUCTION_LAST)
    assert "không sao chép" not in system, (
        "V1 là phép DỜI câu cấm, không phải phép NHÂN BẢN: còn nó ở system thì "
        "phép đo vị trí không còn đo được vị trí"
    )


def test_v1_puts_the_instruction_last_immediately_before_the_payload(monkeypatch):
    """Câu cấm + nhắc hợp đồng JSON phải nằm SÁT khối `Dữ liệu:`.

    Kiểm bằng VỊ TRÍ, không bằng "có mặt": cả hai câu này đã có mặt ở prompt mặc
    định, nên một bài chỉ tìm chuỗi sẽ xanh y nguyên trên V0 và không chứng minh
    được gì về V1.
    """
    system, user = _prompts(monkeypatch, STYLE_INSTRUCTION_LAST)
    assert system + user != DEFAULT_SYSTEM + DEFAULT_USER
    head, _, payload = user.partition("Dữ liệu: ")
    tail = head.rstrip("\n").splitlines()
    assert tail[-1].startswith("Định dạng: "), (
        f"dòng cuối trước dữ liệu phải là nhắc hợp đồng JSON, đang là {tail[-1]!r}")
    assert "không sao chép" in tail[-2], (
        f"câu cấm phải ngay TRƯỚC dòng định dạng, đang là {tail[-2]!r}")
    assert payload.startswith("[{")


def test_v2_adds_exactly_one_input_output_example_pair(monkeypatch):
    system, user = _prompts(monkeypatch, STYLE_FEW_SHOT)
    assert system.count("Đầu vào:") == 1 and system.count("Đầu ra:") == 1, system
    assert user == DEFAULT_USER, "V2 chỉ thêm ví dụ, không được đổi khối dữ liệu"
    assert system + user != DEFAULT_SYSTEM + DEFAULT_USER


def test_v2_keeps_every_default_line_and_appends_the_example(monkeypatch):
    """Mặc định là TIỀN TỐ của V2: biến thể này thêm chỉ dẫn, không viết lại."""
    system, _user = _prompts(monkeypatch, STYLE_FEW_SHOT)
    assert system.startswith(DEFAULT_SYSTEM + "\n"), system


def test_v2_example_is_han_to_vietnamese_and_keeps_the_number(monkeypatch):
    """Cặp mẫu phải dạy đúng ba thứ: chữ Hán vào, tiếng Việt ra, số còn nguyên."""
    system, _user = _prompts(monkeypatch, STYLE_FEW_SHOT)
    example_in = next(line for line in system.splitlines()
                      if line.startswith("Đầu vào:"))
    example_out = next(line for line in system.splitlines()
                       if line.startswith("Đầu ra:"))
    assert any("\u4e00" <= ch <= "\u9fff" for ch in example_in), (
        "đầu vào của ví dụ phải là chữ Hán — nếu không nó không dạy gì về Hán->Việt")
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in example_out), (
        "đầu ra của ví dụ còn chữ Hán thì ví dụ đang DẠY việc chép nguồn")
    assert "12000" in example_in and "12000" in example_out, (
        "số phải GIỮ NGUYÊN ở đầu ra; một ví dụ bỏ số là ví dụ dạy đúng cái sai "
        "cần tránh")


def test_v2_example_does_not_leak_text_from_the_clip(monkeypatch):
    """`不到路费2000` là nội dung CỦA CHÍNH CLIP đang đo — không được làm mẫu.

    Dùng chữ của clip là đưa đáp án vào prompt: mọi con số của lượt này sẽ khác
    lượt trước vì DỮ LIỆU chứ không vì biến thể, và phép so mất nghĩa.
    """
    system, user = _prompts(monkeypatch, STYLE_FEW_SHOT)
    # Không so chuỗi số `2000`: ví dụ cố ý dùng `12000` (giữ số là tính chất của
    # V2), nên `2000` là chuỗi con của nó và một phép `in` sẽ đỏ vô nghĩa.
    for leak in ("不到", "路费"):
        assert leak not in system and leak not in user, leak


def test_v3_numbers_every_payload_line(monkeypatch):
    _system, user = _prompts(monkeypatch, STYLE_NUMBERED)
    for s in BATCH:
        assert f"[{s.i}] {s.text}" in user, s
    assert 'Dữ liệu: [{"i"' not in user, (
        "V3 đổi khối dữ liệu sang dòng có nhãn; mảng JSON còn đó là chưa đổi")
    assert "trả về đúng `i` đó" in user, (
        "phải NÓI RA rằng đầu ra mang đúng `i` của dòng — nếu không thì việc đánh "
        "số chỉ là trang trí")


def test_v3_keeps_the_json_contract_unchanged(monkeypatch):
    """V3 đổi CÁCH TRÌNH BÀY dữ liệu, không đổi hợp đồng đầu ra.

    Dòng `Định dạng:` phải giống NGUYÊN VĂN bản mặc định, vì `parse_batch_response`
    là chỗ duy nhất đọc phản hồi và nó không biết gì về style.
    """
    _system, user = _prompts(monkeypatch, STYLE_NUMBERED)
    format_line = DEFAULT_USER.splitlines()[2]
    assert format_line in user
    assert user.startswith(DEFAULT_USER.splitlines()[0] + "\n")
    assert user != DEFAULT_USER
