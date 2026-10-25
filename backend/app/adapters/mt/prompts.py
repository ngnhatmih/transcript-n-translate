"""Dựng prompt cho engine LLM và parse phản hồi về `Segment`.

Dữ liệu thuần: không import model, không gọi mạng ⇒ test được ở mọi máy. Mọi thứ
có thể sai mà không cần model đều phải bị bắt ở đây, vì đây là chỗ RẺ NHẤT trong
cả giai đoạn để bắt lỗi mà engine thật sinh ra.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import replace

from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term

#: Phiên bản prompt theo engine. Ghi vào `translations.prompt_version` và
#: `llm_calls.prompt_version`, nên đổi prompt PHẢI đổi chuỗi này — nếu không thì
#: không phân biệt được bản dịch cũ và mới khi prompt thay đổi.
#:
#: `p2` (lượt này): thêm câu CẤM chép nguyên văn vào `system_prompt`. Lý do đo
#: được ở `_report_/real-pipeline-fix-report.md` §B: với `p1`, `qwen2.5-3b` chép
#: nguyên chữ Trung cho ĐÚNG chuỗi prompt đó (A: 6/6, seed cố định 3/3, model
#: vừa nạp lại 3/3, bỏ `format:json` 2/2) và chỉ dịch khi prompt đổi; thêm MỘT
#: câu là 5/5 ra tiếng Việt. Không đổi chuỗi này thì các bản dịch echo cũ (`p1`)
#: nằm cùng nhãn với bản dịch mới — đúng thứ dòng này tồn tại để chặn.
PROMPT_VERSION: dict[str, str] = {
    "qwen2.5-3b": "qwen-json-p2",
    "qwen2.5-7b": "qwen-json-p2",
    "opus-mt": "raw-p1",
    # HY-MT 1.5 (Ollama) đi CÙNG đường JSON-batch với hai engine qwen ở trên —
    # `system_prompt`/`user_prompt` là hàm DÙNG CHUNG, không có biến thể riêng cho
    # từng model. Vì vậy hậu tố `-p2` phải trôi cùng chúng: đổi câu CẤM chép
    # nguyên văn trong `system_prompt` mà không đổi cả ba chuỗi thì
    # `translations.prompt_version` không còn phân biệt được bản dịch sinh trước
    # và sau khi đổi prompt.
    #
    # 🔴 Trước lượt này khoá này KHÔNG có, nên `main.py` đóng dấu `"unknown"` vào
    # MỌI hàng dịch của HY-MT (đo trên DB thật: engine `hy-mt-1.5-7b`,
    # `prompt_version = "unknown"`), trong khi engine này là một trong hai engine
    # dịch được chữ ASR. Tiền tố khác `qwen-` để một hàng `translations` tự nói
    # được nó do MODEL nào sinh ra, chứ không chỉ nói prompt đời nào.
    "hy-mt-1.5-7b": "hymt-json-p2",
}

#: Phiên bản prompt của LƯỢT PHA Chimera. Tách khỏi `PROMPT_VERSION` vì nó là
#: một prompt KHÁC, không phải một phiên bản khác của prompt dịch: dùng chung một
#: chuỗi thì `translations.prompt_version` của một lượt pha không phân biệt được
#: với một lượt dịch thường — và cột đó tồn tại đúng để trả lời câu "bản dịch này
#: sinh từ prompt nào".
MERGE_PROMPT_VERSION = "chimera-merge-p1"

# ---------------------------------------------------------------------------
# HATCH THÍ NGHIỆM: các BIẾN THỂ prompt dịch, chọn theo ENGINE + biến môi trường
# ---------------------------------------------------------------------------
#
# Vì sao cần một hatch chứ không sửa thẳng `system_prompt`/`user_prompt`
#     Hai hàm đó DÙNG CHUNG với `qwen2.5-3b`/`qwen2.5-7b`, và số của hai engine
#     đó đã được ghim (`p2`: 5/5 ra tiếng Việt, 0 echo). Một biến thể prompt viết
#     thẳng vào đây là đổi prompt của cả ba engine trong một phép đo chỉ nói về
#     `hy-mt-1.5-7b` — đúng kiểu "sửa mặc định để đo rồi quên sửa lại".
#
# Vì sao là BIẾN MÔI TRƯỜNG chứ không phải một tham số của `TranslateHandler`
#     Prompt được dựng SÂU trong adapter, dưới `TranslateHandler` và dưới cả
#     `_guard_echoes` (mỗi lần dịch lại một đoạn là một prompt mới). Xuyên một
#     tham số qua cả bốn tầng chỉ để đo là sửa chữ ký của code đã ship; biến môi
#     trường thì không xuyên gì cả. Cái giá là nó KHÔNG được phép đọc bừa: đọc
#     theo `engine_id` (xem `experiment_prompt_style`) nên `qwen2.5-3b` nhận
#     prompt mặc định y nguyên từng byte dù biến môi trường có đặt gì.
#
# Vì sao KHÔNG bump `PROMPT_VERSION` cho các biến thể
#     Chưa có biến thể nào được ship (đây là lượt ĐO, việc nhận một biến thể là
#     quyết định riêng). Ghi một chuỗi mới vào `PROMPT_VERSION` là công bố một
#     prompt đã ship; ngược lại, nhận một biến thể mà KHÔNG bump là đúng lỗi mà
#     `PROMPT_VERSION` tồn tại để chặn. Nhãn của lượt đo nằm ở artifact
#     (`prompt_style` trong `data/experiments/.../20261019-prompt-echo-sweep/*.json`).
#     ⇒ Nhận biến thể nào thì bump chuỗi của `hy-mt-1.5-7b` NGAY trong commit đó.
#
# Số đo (clip 115 đoạn `20261019-name-patch-smoke`, 5 thuật ngữ,
# `hy-mt-1.5-7b`, lô 30, `echo_guard` BẬT, mỗi style MỘT lượt qua
# `TranslateHandler`, artifact ở
# `data/experiments/accuracy-pipelines/20261019-prompt-echo-sweep/`):
#
#     style | đoạn phải dịch lại | lô hỏng (EchoProblem) | echo còn lại | chữ Hán | giây
#     v0    | 89                | 0                     | 0            | 0       | 83,03
#     v1    | 89                | 0                     | 0            | 0       | 76,01
#     v2    | 29                | 0                     | 0            | 0       | 68,16
#     v3    | 0                 | 1                     | 0            | 0       | 32,92
#
# Đọc bảng đó, theo đúng thứ tự tin được:
#
# * **V0 tái lập đúng số đã ghim (89)** nên bốn cột so được với nhau. Không tái
#   lập được thì cả lượt đo vô nghĩa — và nó là cột đầu tiên phải đọc.
# * **V1 = V0 (89/89)**: dời câu cấm xuống cuối KHÔNG đổi gì. Đây là phép BÁC BỎ
#   giả thuyết "model bỏ chỉ dẫn nằm ở đầu prompt dài": chính câu đó có tác dụng
#   khi gọi MỘT MÌNH (0/115 đoạn echo ở lô 1), nên thứ làm model chép nguồn là
#   KÍCH THƯỚC LÔ, không phải vị trí chỉ dẫn.
# * **V2 = 89 -> 29**: một cặp mẫu Hán -> Việt cắt 60 lần dịch lại, và 29 lần còn
#   lại nằm HẾT ở lô ĐẦU (ba lô sau 0 đoạn echo; lần chạy lặp lại vẫn đúng 29 nên
#   không phải may). Vẫn ≥ 10 nên CHƯA đạt, và 29 lời gọi singleton giữ wall time
#   ở 60–68 s. Tức ví dụ dạy được phép biến đổi, nhưng không sửa được lô đầu.
# * **V3 hỏng theo kiểu khác**: bỏ mảng JSON làm model trả 22/30 rồi 25/30 mục,
#   `TranslateHandler` hạ cấp xuống dịch từng segment, và một segment vẫn echo ->
#   `EchoProblem`, hàng `failed`, **0** segment được nhận. "0 đoạn dịch lại" của
#   V3 KHÔNG phải thành tích: lượt đó chết trước khi kịp đo, và 32,92 s là thời
#   gian của một lượt hỏng.

#: Style mặc định = ĐÚNG prompt đang ship (`hymt-json-p2`), từng byte. Mọi giá
#: trị khác là biến thể của lượt đo, không phải mặc định.
STYLE_DEFAULT = "v0"
#: V1: câu CẤM chép nguyên văn + nhắc hợp đồng JSON dời xuống CUỐI `user_prompt`,
#: ngay trước khối dữ liệu. Giả thuyết: model nhỏ BỎ chỉ dẫn nằm ở đầu một prompt
#: dài 30 mục; đưa chỉ dẫn tới sát dữ liệu là chỗ nó còn đọc. ĐO: 89 -> 89 lần
#: dịch lại, tức giả thuyết SAI với engine này (xem bảng ở khối trên).
STYLE_INSTRUCTION_LAST = "v1"
#: V2: thêm ĐÚNG MỘT cặp input/output vào cuối `system_prompt`, chữ Hán -> tiếng
#: Việt, GIỮ NGUYÊN CON SỐ. Giả thuyết: model chép nguồn vì nó chưa thấy một lần
#: "chuỗi Hán ở khoá `text` vẫn phải thành tiếng Việt kèm số" — ví dụ là chỉ dẫn
#: rẻ hơn một câu cấm. Cặp mẫu KHÔNG lấy từ clip (xem `_FEW_SHOT_LINES`). ĐO:
#: 89 -> 29 lần dịch lại, và 29 lần đó nằm HẾT ở lô đầu.
STYLE_FEW_SHOT = "v2"
#: V3: khối dữ liệu đổi từ một mảng JSON sang các dòng `[i] <nguồn>`, và prompt
#: đòi đầu ra mang đúng `i` đó; hợp đồng JSON khác nguyên xi. Giả thuyết: mảng
#: JSON dài là thứ model "chép lại" được nguyên khối, còn dòng có nhãn thì buộc
#: nó đọc từng mục và map sang — cùng lý do người ta đánh số dòng bản gốc. ĐO:
#: 22/30 rồi 25/30 mục -> lệch alignment -> hạ cấp -> 1 `EchoProblem`. LOẠI.
STYLE_NUMBERED = "v3"

#: Tập giá trị hợp lệ của hatch, theo đúng thứ tự V0–V3 của lượt đo.
PROMPT_STYLES: tuple[str, ...] = (
    STYLE_DEFAULT, STYLE_INSTRUCTION_LAST, STYLE_FEW_SHOT, STYLE_NUMBERED)

#: Engine DUY NHẤT được phép nhận biến thể. Không phải sở thích: số đo của lượt
#: này (và của `echo_guard`) chỉ có trên `hy-mt-1.5-7b`, còn `opus-mt` echo 0/115
#: nên một biến thể cho nó là một phép đo chưa từng chạy.
EXPERIMENT_PROMPT_ENGINE = "hy-mt-1.5-7b"

#: Tên biến môi trường của hatch. `scripts/smoke_echo_guard.py` đặt nó cho TỪNG
#: lượt chạy (`--styles`); vắng mặt hoặc rỗng = `STYLE_DEFAULT`.
EXPERIMENT_PROMPT_STYLE_ENV = "PHU_DE_MT_PROMPT_STYLE"


def experiment_prompt_style(engine_id: str | None) -> str:
    """Style prompt của MỘT engine: `STYLE_DEFAULT` trừ khi hatch bật cho nó.

    Hàm này là chỗ DUY NHẤT đọc `EXPERIMENT_PROMPT_STYLE_ENV`, và nó đọc biến đó
    SAU khi đã loại mọi engine không phải `EXPERIMENT_PROMPT_ENGINE`. Nhờ thứ tự
    đó, "engine không chọn biến thể thì nhận prompt mặc định" là một tính chất
    của code, không phải một lời hứa: `qwen2.5-3b` (và `engine_id=None`, tức mọi
    người gọi cũ không truyền gì) không đi qua nhánh đọc biến môi trường nào cả.

    Giá trị LẠ ném `ValueError` chứ không lặng lẽ rơi về mặc định. Một lượt đo
    gõ nhầm `v3` thành `v03` mà vẫn chạy sẽ sinh ra bốn artifact, trong đó một
    cái mang nhãn `v03` nhưng là prompt mặc định — và mọi kết luận rút từ bảng
    đó đều sai trong im lặng. Ở đây "không đo được" phải ồn hơn "đo sai".
    """
    if engine_id != EXPERIMENT_PROMPT_ENGINE:
        return STYLE_DEFAULT
    raw = (os.environ.get(EXPERIMENT_PROMPT_STYLE_ENV) or "").strip().lower()
    if not raw:
        return STYLE_DEFAULT
    if raw not in PROMPT_STYLES:
        raise ValueError(
            f"{EXPERIMENT_PROMPT_STYLE_ENV}={raw!r} không phải style đã đo; "
            f"chỉ nhận {list(PROMPT_STYLES)} (rỗng = mặc định)")
    return raw


#: Dòng hợp đồng JSON của lượt dịch. Là HẰNG, không phải f-string, vì nó phải
#: giống NGUYÊN VĂN ở cả mặc định lẫn V3 ("hợp đồng JSON khác nguyên xi" là định
#: nghĩa của V3 — nếu biến thể tự viết lại dòng này thì nó đã đổi hai thứ).
_FORMAT_LINE = 'Định dạng: {"translations": [{"i": <số>, "text": "<bản dịch>"}]}'

#: Dòng hợp đồng ĐẦU RA của kiểu `lines` (xem `parse_lines_response`).
#:
#: Vì sao cần một hợp đồng thứ hai: hợp đồng JSON của dòng trên là thứ **Ollama**
#: bảo đảm bằng grammar-constrained decoding (`format: "json"`), KHÔNG phải thứ
#: model 7B tự làm được. Đo được: cùng `hy-mt`, cùng clip, cùng lô 30, qua một
#: endpoint OpenAI-compatible (không có grammar) thì model trả JSON hỏng cú pháp —
#: mất dấu phẩy giữa hai mục, `{" translations"` thừa dấu cách, một mục viết
#: `"text", "..."` thay vì `"text": "..."` — và hỏng cả ở lô 1 (3/30 lời gọi).
#: Artifact: `data/experiments/accuracy-pipelines/20261025-spike-openai-mt/`.
#:
#: Kiểu dòng không có ngoặc, không có dấu phẩy, nên những lỗi đó không tồn tại;
#: lỗi còn lại là lệch SỐ DÒNG, và nó bị `parse_lines_response` ném thành
#: `AlignmentProblem` — tức vẫn ồn, không âm thầm cắt cụt.
_FORMAT_LINE_LINES = (
    "Định dạng: mỗi mục MỘT dòng, bắt đầu bằng số `i` của mục, sau đó là một dấu "
    "TAB, rồi bản dịch. Không thêm chữ nào khác."
)

#: Câu CẤM CHÉP NGUYÊN VĂN (vá lỗi echo `p1` -> `p2`, xem `PROMPT_VERSION`).
#: Hàm chứ không phải hằng vì nó mang `target_lang`; `system_prompt` và V1 dùng
#: CÙNG một chuỗi, nên câu này không thể trôi thành hai dị bản.
def _no_copy_lines(target_lang: str) -> list[str]:
    return [
        f"TUYỆT ĐỐI không sao chép nguyên văn bản gốc: mỗi 'text' phải là câu "
        f"{target_lang}, không được để lại chữ của bản gốc."
    ]


def _role_lines(target_lang: str, *, contract: str = "json") -> list[str]:
    """Ba dòng VAI + quy tắc, phần chung của mọi style.

    `contract` chọn câu hợp đồng ĐẦU RA: `json` (mặc định — byte-identical với
    trước lượt đo, có test ghim) hay `lines`. Hai câu này KHÔNG được cùng xuất
    hiện: một prompt vừa đòi JSON vừa đòi dòng thì model chọn cái nào cũng là
    prompt chưa đo.

    Giá trị lạ NÉM, không rơi về mặc định: một engine khai hợp đồng không tồn tại
    mà vẫn chạy sẽ sinh ra artifact mang nhãn sai, đúng loại lỗi `p1`/`p2` từng
    làm cả một bảng kết luận phải viết lại.
    """
    if contract == "json":
        format_line = "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác."
    elif contract == "lines":
        format_line = "Trả về DUY NHẤT các dòng bản dịch, không thêm chữ nào khác."
    else:
        raise ValueError(f"hợp đồng đầu ra lạ: {contract!r} (chỉ nhận 'json', 'lines')")
    return [
        f"Bạn là dịch giả chuyên nghiệp sang {target_lang}.",
        "Dịch sát nghĩa, giữ nguyên văn phong và mức trang trọng của bản gốc.",
        format_line,
    ]


def _glossary_lines(glossary: list[Term]) -> list[str]:
    """Các dòng glossary của prompt dịch.

    Người gọi chỉ gọi hàm này khi `glossary` KHÁC rỗng (`system_prompt`): nhắc tới
    thuật ngữ khi không có cái nào là mời model bịa ra ràng buộc.
    """
    lines = ["Bắt buộc dùng đúng các thuật ngữ sau:"]
    lines.extend(f"- {t.term} => {t.translation}" for t in glossary)
    return lines


#: Cặp input/output DUY NHẤT của V2: chữ Hán -> tiếng Việt, và CON SỐ `12000`
#: nằm nguyên ở đầu ra. Ba tính chất, mỗi tính chất một lý do:
#:
#: * **Giữ số** — đây là thứ model hay làm hỏng nhất khi nó "dịch" một câu có
#:   giá tiền; một ví dụ bỏ số là ví dụ dạy đúng cái sai cần tránh.
#: * **Không lấy từ clip** — `不到路费2000` là nội dung của chính clip đang đo;
#:   dùng nó làm mẫu là rò rỉ đáp án vào prompt và mọi con số của lượt này không
#:   còn so sánh được với lượt trước (prompt khác đi vì dữ liệu, không vì biến
#:   thể). Câu ở đây là một câu bịa, ngữ cảnh hàng rau ngoài chợ.
#: * **Đúng hợp đồng** — mẫu viết ra ĐÚNG hình dạng `{"translations": [...]}` mà
#:   `parse_batch_response` đọc, nếu không nó dạy model một định dạng thứ hai.
_FEW_SHOT_LINES = [
    "Ví dụ (đầu vào -> đầu ra; số 12000 phải giữ nguyên):",
    'Đầu vào: {"translations": [{"i": 1, "text": "市场上青菜一斤12000"}]}',
    'Đầu ra: {"translations": [{"i": 1, "text": "Ở chợ, rau cải một cân '
    'giá 12000"}]}',
]


def system_prompt(glossary: list[Term], *, target_lang: str,
                  engine_id: str | None = None) -> str:
    """Vai trò + quy tắc + glossary. Rỗng glossary thì KHÔNG nhắc tới thuật ngữ.

    Nhắc tới glossary khi không có thuật ngữ nào là mời model bịa ra ràng buộc.

    Câu CUỐI là bản vá lỗi DỊCH IM LẶNG (xem `PROMPT_VERSION`: `p1` -> `p2`). Ba
    dòng đầu chỉ nói VAI và ĐỊNH DẠNG; không dòng nào nói "đầu ra phải ở ngôn ngữ
    đích", mà `user_prompt` thì kết thúc bằng một mảng JSON toàn chữ Trung — với
    `qwen2.5:3b` (Q4), continuation rẻ nhất là chép lại chính mảng đó. Đo được:
    `p1` echo 6/6, `p2` ra tiếng Việt 5/5, cùng batch, cùng `temperature=0.1`.

    Câu này để CUỐI (không phải ngay sau dòng đầu) vì đó ĐÚNG là vị trí đã đo:
    đặt giữa prompt là một biến thể CHƯA đo, và một phép sửa prompt không có số
    đo thì không được phép tự nhận là đã sửa.

    `engine_id` chỉ để mở hatch biến thể (`experiment_prompt_style`). Không truyền
    ⇒ mặc định, byte-identical với trước lượt đo; đó là đường MỌI engine khác đi.

    Hai biến thể chạm vào hàm này, và mỗi cái đổi ĐÚNG một thứ:
    `STYLE_INSTRUCTION_LAST` BỎ câu cấm ở đây (nó được dời xuống cuối
    `user_prompt` — dời, không phải nhân bản, nếu không thì phép đo vị trí không
    còn là phép đo vị trí); `STYLE_FEW_SHOT` GIỮ NGUYÊN mọi dòng rồi NỐI thêm cặp
    mẫu, nên prompt mặc định là tiền tố của nó.
    """
    style = experiment_prompt_style(engine_id)
    lines = _role_lines(target_lang)
    if glossary:
        lines.extend(_glossary_lines(glossary))
    if style != STYLE_INSTRUCTION_LAST:
        lines.extend(_no_copy_lines(target_lang))
    if style == STYLE_FEW_SHOT:
        lines.extend(_FEW_SHOT_LINES)
    return "\n".join(lines)


def system_prompt_lines(glossary: list[Term], *, target_lang: str) -> str:
    """`system_prompt` nhưng cho hợp đồng `lines`: vai + glossary + cấm chép.

    Không nhận `engine_id` và không đi qua `experiment_prompt_style`: các style
    `V0..V3` đều được đo TRÊN hợp đồng JSON, nên cho chúng chạm vào prompt dòng
    là trộn hai biến số vào một phép đo. Engine dùng hợp đồng này có đúng MỘT
    prompt, và đó là điều kiện để con số của nó so được với nhau.
    """
    lines = _role_lines(target_lang, contract="lines")
    if glossary:
        lines.extend(_glossary_lines(glossary))
    lines.extend(_no_copy_lines(target_lang))
    return "\n".join(lines)



def user_prompt(batch: list[Segment], *, source_lang: str, target_lang: str,
                engine_id: str | None = None) -> str:
    """Lượt người dùng: chỉ dẫn ngắn + khối dữ liệu.

    Mặc định (không `engine_id`, hoặc engine không bật hatch) giống NGUYÊN VĂN
    từng byte bản trước lượt đo — có bài test ghim cả hai chuỗi.

    Biến thể chạm vào hàm này:
    * `STYLE_INSTRUCTION_LAST` chèn câu cấm chép + dòng hợp đồng JSON vào CUỐI,
      ngay trước `Dữ liệu:` (câu cấm bị bỏ khỏi `system_prompt` để đây là phép
      dời vị trí, không phải phép thêm chỉ dẫn).
    * `STYLE_NUMBERED` đổi khối dữ liệu từ mảng JSON sang các dòng `[i] <nguồn>`
      và thêm MỘT câu đòi đầu ra mang đúng `i`; dòng `Định dạng:` giữ nguyên
      (`_FORMAT_LINE`) nên hợp đồng JSON không đổi.
    """
    style = experiment_prompt_style(engine_id)
    if style == STYLE_NUMBERED:
        head = [
            f"Dịch từng mục từ {source_lang} sang {target_lang}.",
            "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.",
            _FORMAT_LINE,
            "Mỗi dòng dữ liệu bắt đầu bằng `[i]`; trả về đúng `i` đó trong từng "
            "mục.",
        ]
        payload = "\n".join(f"[{s.i}] {s.text}" for s in batch)
        return "\n".join(head) + f"\nDữ liệu:\n{payload}"

    items = [{"i": s.i, "text": s.text} for s in batch]
    lines = [
        f"Dịch từng mục từ {source_lang} sang {target_lang}.",
        "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.",
    ]
    if style == STYLE_INSTRUCTION_LAST:
        lines.extend(_no_copy_lines(target_lang))
    lines.append(_FORMAT_LINE)
    lines.append(f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}")
    return "\n".join(lines)


def user_prompt_lines(batch: list[Segment], *, source_lang: str,
                      target_lang: str) -> str:
    """Lượt người dùng cho hợp đồng `lines`: khối dữ liệu cũng bằng dòng.

    Khối dữ liệu dùng CÙNG dấu TAB mà đầu ra phải dùng — một ví dụ sống ngay
    trong prompt, rẻ hơn mọi lời giải thích về định dạng, và không đòi model suy
    ra hình dạng đầu ra từ một mảng JSON (đó chính là chỗ nó chép lại nguồn).
    """
    head = [
        f"Dịch từng mục từ {source_lang} sang {target_lang}.",
        "Giữ nguyên số thứ tự của từng mục và trả đúng bấy nhiêu dòng.",
        _FORMAT_LINE_LINES,
    ]
    payload = "\n".join(f"{s.i}\t{s.text}" for s in batch)
    return "\n".join(head) + f"\nDữ liệu:\n{payload}"


#: Model thật hay bọc JSON trong ```json ... ``` — đây là failure mode phổ biến
#: chứ không phải đầu vào bất thường, nên nó phải parse được.
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")

#: Tên khoá TƯƠNG ĐƯƠNG cho hai trường của một mục. Đọc theo thứ tự này, nên tên
#: đầu tiên thắng khi model trả nhiều tên cùng lúc.
#:
#: Vì sao cần (A3, đo được): model trả `{"i": 2, "Text": "..."}` — chữ T hoa —
#: cho MỘT trong 8 mục, 7 mục kia là tiếng Việt tốt, và bản cũ ném
#: `ValueError: mục thiếu 'i' hoặc 'text' không phải chuỗi` rồi **vứt cả 8 câu**.
#: Nặng hơn: lượt gọi ĐẦU TIÊN sau khi sửa prompt (xem `system_prompt`) cũng trả
#: 8/8 tiếng Việt kèm MỘT khoá `"Text"` — tức phép nới này là thứ quyết định cả
#: lô được GIỮ hay bị vứt, không phải một chi tiết cú pháp.
#:
#: Nới tới đâu là cố ý: chỉ những tên THẬT SỰ TƯƠNG ĐƯƠNG. `txt`, `nội dung`,
#: hay một khoá bất kỳ KHÔNG được nhận — nhận chúng là biến "engine trả sai hợp
#: đồng" thành "ta đoán ý engine", và một `null` sẽ thành phụ đề.
_I_KEYS = ("i", "index", "id")
_TEXT_KEYS = ("text", "translation")



def _normalised_keys(item: dict) -> dict:
    """Khoá của một đối tượng JSON, đã hạ chữ thường và cắt khoảng trắng.

    Hai LƯỢT, và thứ tự lượt là hợp đồng: lượt 1 chỉ nhận khoá viết ĐÚNG chữ
    thường (chuẩn), lượt 2 `setdefault` cho các cách viết khác. Nhờ vậy
    `{"Text": "SAI", "text": "đúng"}` luôn cho `"đúng"` bất kể model đặt khoá nào
    trước — chọn theo thứ tự dict là chọn theo thứ tự model sinh ra, tức không
    tất định giữa hai lần chạy cùng prompt.
    """
    out: dict = {}
    for key, value in item.items():
        if key == key.strip().lower():
            out[key] = value
    for key, value in item.items():
        out.setdefault(key.strip().lower(), value)
    return out


def _pick(item: dict, names: tuple[str, ...]) -> tuple[bool, object]:
    """`(có mặt, giá trị)` của tên khoá ĐẦU TIÊN trong `names` xuất hiện.

    `item` phải đã qua `_normalised_keys`; `names` là các tên đã hạ chữ thường.
    """
    for name in names:
        if name in item:
            return True, item[name]
    return False, None


def parse_batch_response(raw: str, batch: list[Segment]) -> list[Segment]:
    """Ghép bản dịch vào ĐÚNG segment đầu vào, giữ nguyên timestamp/người nói.

    Đây là chỗ DUY NHẤT biến phản hồi engine thành `Segment`, nên mọi lệch
    alignment phải ném ở đây: trả về một list ngắn hơn là đúng kiểu thất bại âm
    thầm làm phụ đề lệch chỗ mà không có triệu chứng nào.

    Khoá được đọc KHÔNG phân biệt hoa/thường và chấp nhận tên tương đương
    (`_I_KEYS`, `_TEXT_KEYS`) — lý do đo được ở docstring của hai hằng đó. Kiểu
    của GIÁ TRỊ thì vẫn nghiêm: `text` không phải chuỗi là `ValueError`, không
    bao giờ được `str()` hoá thành phụ đề.
    """
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"engine không trả JSON hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")
    top = _normalised_keys(data)
    if not isinstance(top.get("translations"), list):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")

    got: dict[int, str] = {}
    for item in top["translations"]:
        if not isinstance(item, dict):
            raise ValueError(f"mục không phải đối tượng JSON: {item!r}")
        fields = _normalised_keys(item)
        has_i, raw_i = _pick(fields, _I_KEYS)
        _has_text, raw_text = _pick(fields, _TEXT_KEYS)
        if not has_i or not isinstance(raw_text, str):
            # Vẫn giữ ĐÚNG câu chữ cũ: nó là hợp đồng grep được của tầng gọi.
            raise ValueError(f"mục thiếu 'i' hoặc 'text' không phải chuỗi: {item!r}")
        try:
            key = int(raw_i)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'i' không phải số nguyên: {raw_i!r}") from exc
        got[key] = raw_text

    expected_ids = [s.i for s in batch]
    # ĐẾM số mục, không chỉ so TẬP id: `got` là dict nên id trùng bị nuốt trước khi
    # so sánh, và một mục thừa là dấu hiệu engine lẫn lộn — Task 11 phải thử lại cả
    # lô thay vì âm thầm nhận bản dịch thứ hai của cùng một id.
    if len(top["translations"]) != len(batch):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả {len(top['translations'])} mục, cần {len(batch)}")

    if sorted(got) != sorted(expected_ids):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả id {sorted(got)}, cần {sorted(expected_ids)}")

    # Duyệt theo batch để thứ tự đầu ra LUÔN bằng thứ tự đầu vào, kể cả khi model
    # trả mục xáo trộn.
    #
    # `replace` chứ KHÔNG dựng `Segment(...)` bằng tay: dựng tay chỉ chép 6/13
    # field và nuốt `emotion`, `events`, `avg_logprob`, `no_speech_prob`,
    # `suspect`, `t`, `qa` (đúng lỗi đã bị bắt ở review Task 7). Dịch chỉ được
    # đổi `text`; mọi thứ khác — kể cả `words` — là dữ liệu của bản gốc.
    return [replace(s, text=got[s.i]) for s in batch]


#: Đầu một dòng của hợp đồng `lines`: số `i`, có thể bọc trong `[]`, rồi dấu ngăn
#: cách. Nới ĐÚNG chỗ model hay vi phạm (`[12]`, `12.`, `12:`, `12 -`, thụt đầu
#: dòng), nhưng không nới chỗ quyết định alignment.
_LINE_HEAD = re.compile(r"^\s*\[?\s*(\d{1,6})\s*\]?\s*")

#: Dấu ngăn cách được nhận sau `i`. TAB đứng đầu vì đó là thứ prompt yêu cầu;
#: phần còn lại là những gì model thật đã trả thay cho TAB.
_LINE_SEPARATORS = " \t|:=.->\u2013\u2014"


def parse_lines_response(raw: str, batch: list[Segment]) -> list[Segment]:
    """Ghép bản dịch từ hợp đồng `lines` — một dòng `<i>` TAB `<bản dịch>` mỗi mục.

    Vì sao có hàm này: xem `_FORMAT_LINE_LINES`. Tóm tắt: hợp đồng JSON được
    **Ollama** bảo đảm bằng grammar, nên qua một endpoint không có grammar thì
    model viết hỏng cú pháp. Kiểu dòng không có ngoặc và dấu phẩy, nên những lỗi
    đó không tồn tại.

    Ba bất biến, giống hệt `parse_batch_response` — và đây là lý do hàm này KHÔNG
    được nới hơn:
    * **Đủ số dòng** — thiếu một dòng là `AlignmentProblem`, không bao giờ trả list
      ngắn hơn đầu vào (mất một dòng phụ đề mà không có triệu chứng là đúng kiểu
      thất bại `AlignmentProblem` sinh ra để chặn);
    * **Đúng tập id** — id lạ hay id thiếu đều ném;
    * **Không nuốt chữ** — một dòng KHÔNG mang id nằm giữa khối bản dịch là lỗi,
      không phải lời dẫn: model xuống dòng giữa một câu mà ta lặng lẽ bỏ dòng sau
      thì bản dịch mất nửa câu mà số dòng vẫn "đủ".

    Lời dẫn TRƯỚC dòng đầu tiên (ví dụ "Dưới đây là bản dịch:") được bỏ qua — đó
    là thứ model hay thêm và nó không mang thông tin gì.
    """
    text = _FENCE.sub("", raw.strip()).strip()
    got: dict[int, str] = {}
    order: list[int] = []
    started = False
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _LINE_HEAD.match(line)
        if match is None:
            if started:
                raise ValueError(
                    f"dòng không mang id nằm giữa khối bản dịch: {line!r}")
            continue                      # lời dẫn trước khối: bỏ qua
        started = True
        index = int(match.group(1))
        body = line[match.end():].lstrip(_LINE_SEPARATORS).strip()
        if not body:
            raise ValueError(f"mục {index} có id nhưng không có bản dịch: {line!r}")
        if index in got:
            raise ValueError(f"id {index} xuất hiện hai lần trong đầu ra")
        got[index] = body
        order.append(index)

    expected_ids = [s.i for s in batch]
    if len(order) != len(batch):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả {len(order)} dòng, cần {len(batch)}")
    if sorted(got) != sorted(expected_ids):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả id {sorted(got)}, cần {sorted(expected_ids)}")
    return [replace(s, text=got[s.i]) for s in batch]


def merge_system_prompt(glossary: list[Term], *, target_lang: str,
                        run_count: int) -> str:
    """Vai trò của LƯỢT PHA: GỘP, không dịch lại từ đầu.

    Câu CUỐI giữ nguyên câu CẤM CHÉP NGUYÊN VĂN của `system_prompt`, và ở đây nó
    còn cần hơn: lượt pha nhận được N bản đã có sẵn, nên continuation rẻ nhất của
    một model yếu là chép lại nguyên ứng viên đầu tiên — kể cả khi cả N ứng viên
    đều là chữ Hán. Câu cấm là thứ duy nhất nói ra rằng việc đó không được phép.
    """
    lines = [
        f"Bạn là biên tập viên phụ đề {target_lang}.",
        f"Bạn nhận được {run_count} bản dịch ứng viên cho CÙNG một lô phụ đề.",
        "Với mỗi mục, viết MỘT bản hợp nhất: giữ nội dung đúng nhất, câu chữ tự "
        "nhiên nhất, và NGẮN nhất trong số các ứng viên.",
        "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác.",
    ]
    if glossary:
        lines.append("Bắt buộc dùng đúng các thuật ngữ sau:")
        lines.extend(f"- {t.term} => {t.translation}" for t in glossary)
    lines.append(
        f"TUYỆT ĐỐI không sao chép nguyên văn bản gốc: mỗi 'text' phải là câu "
        f"{target_lang}, không được để lại chữ của bản gốc.")
    return "\n".join(lines)


def merge_user_prompt(batch: list[Segment],
                      candidates: tuple, *, anchor: str | None,
                      source_lang: str, target_lang: str) -> str:
    """Dữ liệu của lượt pha: mỗi mục có bản NGUỒN + MỌI ứng viên, gọi tên theo `id`.

    Mỏ neo được NÓI RA ("ỨNG VIÊN MỎ NEO"), không chỉ được xếp đầu: `anchor_index`
    đã chọn nó bằng một luật tất định, và luật đó chỉ có tác dụng nếu lượt pha biết
    nó là gì. Một lượt pha không biết mỏ neo sẽ tự chọn lại — tức là có hai chỗ
    quyết định, và chỗ thứ hai không ai ghi lại được.

    Định dạng ĐẦU RA giữ nguyên chuỗi của `user_prompt`, nên `parse_batch_response`
    vẫn là chỗ DUY NHẤT biến phản hồi engine thành `Segment` — cho cả lượt dịch
    lẫn lượt pha.
    """
    ids = [cid for cid, _segs in candidates]
    texts: dict[str, dict[int, str]] = {}
    for cid, segs in candidates:
        texts[cid] = {s.i: s.text for s in segs}

    items: list[dict] = []
    for s in batch:
        item: dict = {"i": s.i, "nguon": s.text}
        for cid in ids:
            item[cid] = texts.get(cid, {}).get(s.i, "")
        items.append(item)

    return (
        f"Pha {len(ids)} bản dịch ứng viên ({', '.join(ids)}) từ {source_lang} "
        f"sang {target_lang} thành MỘT bản.\n"
        "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.\n"
        f"ỨNG VIÊN MỎ NEO: {anchor or '(không có)'}\n"
        'Định dạng: {"translations": [{"i": <số>, "text": "<bản hợp nhất>"}]}\n'
        f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}"
    )
