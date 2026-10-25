# Giai đoạn 2 — Workspace 2 (dịch) — thiết kế

**Ngày:** 2026-09-26
**Trạng thái:** chờ người dùng duyệt trước khi viết plan
**Spec nền (không thay thế):** `docs/superpowers/specs/2026-09-25-phu-de-lab-design.md` (v3)
**Tiền đề đã ship:** Giai đoạn 1a — backend workspace 1, nhánh `gd1a-backend`, HEAD `fc522a2`, suite **517 passed**

Spec này **không** lặp lại spec nền. Nó chốt phạm vi Giai đoạn 2, các quyết định còn để mở, và những chỗ spec nền
nói một đằng còn mã đã ship một nẻo.

---

## 1. Mục tiêu & phạm vi

**Mục tiêu:** backend Workspace 2 chạy được đầu-cuối — văn bản đã bóc băng → bản dịch tiếng Việt, có glossary,
có QA tất định, xuất được phụ đề — **đối xứng với Giai đoạn 1a**: chỉ backend, có test, và **có ít nhất một lần
chạy thật được ghi lại bằng số**.

**Trong phạm vi:**

| Hạng mục | Quyết định |
|---|---|
| Engine dịch | **OPUS-MT** (in-process, CPU) và **Qwen2.5-3B** qua Ollama — **cả hai chạy thật** |
| HY-MT1.5 | **Hoãn** — spec nền §12 tự đánh dấu rủi ro Cao (GGUF cộng đồng + `ollama create`). Vẫn có spec trong registry với `available: false` |
| Chế độ Chimera | **Hoãn cùng HY-MT1.5** — spec nền §8.7.5 định nghĩa nó *chỉ* cho HY-MT1.5 (đường hậu kiểm + vá tìm-thay-thế) |
| Glossary | **Đầy đủ**: bảng + CRUD + nhét system prompt cho Qwen + đếm bản dịch bị ảnh hưởng khi glossary đổi + job "Dịch lại · do glossary đổi" |
| Frontend | **Không** — như Giai đoạn 1a |
| TypeSafe/Jev | **Không** nằm trong app. Đây là quyết định của người dùng, ghi lại để người đọc sau không tưởng là thiếu |

**Ngoài phạm vi (hoãn có chủ ý):** HY-MT1.5 · Chimera · toàn bộ frontend · glossary tự đề xuất bằng LLM
(spec nền §13 dòng 838) · dịch nhiều đích ngôn ngữ ngoài `vi`.

---

## 2. Kiến trúc

Giữ nguyên khuôn hexagonal-lite của 1a. Không tạo tầng mới.

```
domain/     thuần, stdlib  →  mt.py · alignment.py · glossary_match.py · mt_qa.py
ports/      chỉ Protocol   →  MtEngine · (mở rộng) Repos
adapters/   hiện thực      →  mt/opus_mt.py · mt/ollama_mt.py · mt/prompts.py
pipeline/   điều phối      →  translate.py (TranslateHandler)
api/        HTTP           →  routes_translations.py · routes_glossary.py
```

**Ràng buộc tầng đã có guard, phải giữ:** `app/domain/` chỉ import stdlib (allowlist hẹp + namespace `app.domain`);
`app/ports/` chỉ chứa `Protocol`, không hiện thực; **không** file nào dưới `app/api/` được dùng `sqlite3`,
`db_path` hay `_connect(` — đi qua port.

### 2.1 `domain/`

- **`mt.py`** — `batch_segments(segments, budget) -> list[list[Segment]]`. Ngân sách **tính bằng ký tự** của phần
  văn bản nguồn (đơn vị duy nhất mà mọi engine đều có, kể cả OPUS-MT vốn không có token count), và **cấu hình
  được**. Giá trị cụ thể **đo rồi chốt** (§12). Một lô **luôn** chứa ít nhất một segment, kể cả khi segment đó
  vượt ngân sách — không có lô rỗng và không có segment bị bỏ. Hàm thuần ⇒ test được không cần model.
  Bất biến: ghép các lô theo thứ tự = đầu vào, **đúng thứ tự**, không lô rỗng, không segment nào xuất hiện hai lần.
- **`alignment.py`** — `check_alignment(src, out) -> None`, ném `AlignmentProblem` (có `.expected_ids`,
  `.got_ids`, `.reason`) khi số lượng / id / thứ tự không khớp. Thuần.
  *(Bản trước của spec có nhắc `split_batches_for_repair(...)`. Hàm đó **không được làm** — bước hạ cấp xuống dịch
  từng segment nằm **ngoài** module này, trong `TranslateHandler` (Task 11), vì nó cần gọi engine chứ không thuần.
  Spec đã sửa cho khớp mã, thay vì thêm một hàm chỉ để khớp spec.)*
- **`glossary_match.py`** — `terms_in(segment, glossary) -> list[Term]`;
  `affected_segments(segments, old_glossary, new_glossary) -> list[int]`. Thuần. Đây là thứ tab Thuật ngữ cần.
- **`mt_qa.py`** — QA tất định sau dịch, trả `list[QaIssue]`. Thuần.

### 2.2 `ports/`

- **`MtEngine`** (Protocol):
  ```python
  def translate(self, batch: list[Segment], glossary: list[Term], opts: MtOpts) -> list[Segment]: ...
  def release(self) -> None: ...          # BẮT BUỘC idempotent (hợp đồng R42 của 1a)
  def supports_glossary(self) -> bool: ...
  ```
- **`Repos`** mở rộng: `add_translation`, `get_translation`, `list_translations_for_transcript`,
  `update_translation_segments`, `set_translation_status`, các phương thức glossary
  (`add_term`, `list_terms`, `update_term`, `bump_glossary_version`).
  **Không** Protocol nào là `runtime_checkable`, và không chỗ nào `isinstance`-kiểm port ⇒ thêm phương thức là an toàn.

### 2.3 `adapters/mt/`

- **`prompts.py`** — dựng prompt theo engine. **Dữ liệu thuần** (chuỗi vào/ra), test được không cần model.
  Mỗi engine có `PROMPT_VERSION` riêng (chuỗi), ghi vào `translations.prompt_version` và `llm_calls.prompt_version`.
- **`opus_mt.py`** — transformers/Marian, in-process, CPU. Dịch **từng segment rời** (Marian không có ngữ cảnh).
  `supports_glossary() -> False`. Không có token count ⇒ `tokens_in/out = NULL`.
- **`ollama_mt.py`** — HTTP tới Ollama. `supports_glossary() -> True`. Đọc `prompt_eval_count`/`eval_count` từ
  phản hồi để ghi `llm_calls`.

---

## 3. Luồng một lần dịch

`POST /api/translations` → ghi dòng `translations` (`status='queued'`) + job `translate:<engine>`.

Worker vào phase `translate:<engine>` → `TranslateHandler`:

1. Đọc segment nguồn từ `transcripts.segments` + glossary **đã duyệt** (`approved = 1`).
2. `batch_segments(...)` chia lô.
3. Với **mỗi lô**: dựng prompt → gọi engine → **kiểm alignment** → ghi kết quả → **checkpoint**.
4. Hết lô: chạy QA tất định, ghi `qa_issues`, `tokens_in/out`, `duration_ms` → `status='done'` → job `done`.

**Checkpoint** ghi vào `translations.segments`. Phân chia trách nhiệm cho rõ (đã bị hiểu sai một lần khi làm Task 6):
**handler** (`TranslateHandler`) giữ danh sách trong bộ nhớ, **cộng dồn** theo thứ tự (`done + lô mới`), rồi gọi
`update_translation_segments(id, toàn_bộ_danh_sách)`; **adapter** chỉ ghi **đúng danh sách được đưa** — nó **không**
tự nối thêm. Vì vậy `len(segments)` **chính là** tiến độ; `Job.progress = len(done) / len(total)`.
Ghi checkpoint với `id` không tồn tại **phải ném `NotFound`**, không được im lặng thành công — nếu không thì một id
sai sẽ nuốt cả lô mà job vẫn báo `done`.
**Không** cần bảng `translation_segments` mới.

**Hủy:** kiểm `cancel_requested` **giữa các lô**; dừng và **giữ nguyên phần đã dịch** (không xoá công đã làm).
`status='cancelled'`.

**Retry:** chạy lại từ **lô đầu tiên chưa có kết quả**, không dịch lại từ đầu. `attempts` tăng trên job.

**Bất biến then chốt:** `translations.segments` **chỉ** chứa bản dịch khớp **đúng id** segment nguồn, theo đúng thứ
tự. Phần chưa dịch biểu diễn bằng **thiếu dòng**, **không bao giờ** bằng dòng rỗng và **không bao giờ** bằng ghép
lệch thứ tự.

---

## 4. Hợp đồng engine và chính sách lệch alignment

### 4.1 Prompt

- **Qwen2.5 qua Ollama.** system = vai trò + quy tắc xưng hô + glossary dạng `nguồn ⇒ đích`;
  user = lô JSON **có `id`**; yêu cầu trả JSON **cùng `id`**. Dùng chế độ JSON của Ollama, nhiệt độ thấp.
- **OPUS-MT.** Không prompt, dịch từng segment rời, **không glossary**. Vì `supports_glossary() == False`,
  `mt_qa` **phải** sinh cờ *"engine này không đảm bảo glossary"* — không được im lặng cho qua (spec nền §8.7.2:
  "OPUS-MT … UI cảnh báo").

### 4.2 Chính sách lệch alignment (failure mode thật của mọi engine LLM)

Ba bước, dừng ở bước nào thành công ở đó:

- **a. Retry trong cùng lô**, tối đa **1 lần**, kèm prompt sửa lỗi nói rõ *"trả đúng N mục, đúng id"*.
- **b. Hạ cấp lô đó** xuống **dịch từng segment**. (Lô lớn là lúc LLM hay hỏng nhất.)
- **c. Vẫn sai** ⇒ đánh dấu **lô thất bại**, ghi rõ **segment id nào chưa có bản dịch**, job → `FAILED` với
  thông báo hành động được.

Mỗi bước phải **đếm được** và ghi vào `llm_calls` + `log_tail`, để biết engine nào hay hỏng alignment.

---

## 5. VRAM — phối hợp với Ollama

Đây là chỗ hai cơ chế chạm nhau: `SingleGpuGovernor` của 1a đổ model bằng cách gọi **releaser** khi **đổi giai
đoạn**; Ollama giữ model theo `keep_alive` và **tự quản VRAM trong một tiến trình riêng**.

**Quyết định:**

- `OllamaMtEngine` **đăng ký releaser với governor**, và releaser đó **gọi Ollama để đổ model** ⇒ **một đầu mối
  duy nhất** là governor; không có hai bên cùng giành VRAM.
- `keep_alive` khi **đang dịch** đặt đủ dài để **không nạp lại model giữa các lô**. Nạp Qwen2.5-3B tốn vài giây và
  là **chi phí lớn nhất** của cả luồng.
- Ollama **không chạy** ⇒ engine `available: false`, và job **fail sớm ở tầng API**, không đợi vào worker mới hỏng
  (bài học I-3 của 1a).

**Điều chưa đo được và sẽ đo trước khi vào plan:** cơ chế đổ model của Ollama (`keep_alive: 0`) và thời gian nạp
thật. Phải **đo bằng `ollama ps`** trên bản Ollama thực cài, **không viết theo trí nhớ**. Nếu đo ra khác, mục này
đổi trước khi lập plan.

---

## 6. Dữ liệu — migration là bắt buộc

**Hiện trạng đã đọc trong mã (không suy đoán theo spec):** `translations` đã có `transcript_version`, `engine`,
`target_lang`, `segments` (một blob JSON), `prompt_version`, `glossary_version`, `qa_issues`, `tokens_in/out`,
`duration_ms`. `glossary` đã có `approved`. `llm_calls` đã có sẵn. `jobs` đã có `progress REAL`.

**Hai vấn đề phải xử lý:**

1. **`translations` không có cột `status`.** Trạng thái `queued/running/done/failed/cancelled` phải đọc được.
   ⇒ thêm cột.
2. **`init_schema()` chỉ chạy `CREATE TABLE IF NOT EXISTS` rồi ghi đè `schema_meta.version`; không có migration.**
   Hệ quả: thêm cột vào bảng **đã tồn tại** sẽ **âm thầm không xảy ra** trên DB cũ, trong khi version vẫn bị ghi
   thành số mới ⇒ DB Giai đoạn 1a đang nằm trên máy sẽ chết với `no such column`. Đây là lỗ hổng của 1a, và
   Giai đoạn 2 là phase **đầu tiên** cần đổi schema.

**Quyết định:**

- Bump `SCHEMA_VERSION` lên **2**.
- Viết **bước migration thật**: đọc version hiện có trong `schema_meta`, áp các bước **có thứ tự** và
  **idempotent**, rồi mới ghi version mới.
- Thêm `translations.status TEXT NOT NULL DEFAULT 'queued'`.
- Test migration bằng cách **dựng một DB phiên bản 1** (schema cũ nguyên văn) rồi migrate, và khẳng định: cột mới
  có mặt · **dữ liệu cũ còn nguyên** · chạy migration **hai lần** không hỏng.

---

## 7. API

Theo đúng spec nền §11:

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| `GET` | `/api/translations?transcript_id=` | N bản dịch, **cờ `stale` tính sẵn** |
| `PATCH` | `/api/translations/{id}` | sửa tay một bản dịch |
| `GET` · `POST` · `PATCH` | `/api/glossary` | quản lý glossary |
| `POST` | `/api/transcripts/{id}/approve` | duyệt → chuyển WS2 |

**Điểm vênh phải chốt — export.** Spec ghi `GET /api/export/{translation_id}?format=&bilingual=`; 1a đã ship
`POST /api/export` + `GET /api/export/{job_id}/download`. **Quyết định:** thêm route **đúng spec**, **giữ** route cũ,
và ghim bằng test rằng **cả hai cho ra cùng nội dung** cho cùng một bản dịch (`artifact_name()` đã dùng chung nên
hai đường không thể trôi khỏi nhau). Bỏ route cũ là phá thứ đang chạy mà không có gì bù ⇒ để phase sau quyết.

---

## 8. QA tất định sau dịch (không tốn model)

Ghi vào `translations.qa_issues`:

- **CPS** trên bản dịch (ngưỡng đo được đã có từ 1a).
- **Tỉ lệ độ dài** — bắt bản dịch cụt hoặc lan man.
- **Thuật ngữ bắt buộc có mặt** (glossary đã duyệt) và **thuật ngữ cấm**.
- **Cờ engine không hỗ trợ glossary** (OPUS-MT) — thông tin, không phải lỗi.
- **Cờ `stale`** — một bản dịch là `stale` khi `transcripts.version` hiện tại **lớn hơn** `translations.transcript_version`
  đã ghi lúc dịch. Cờ này **tính sẵn** trong `GET /api/translations?transcript_id=`, không để client tự suy.

### 8.1 Glossary đổi ⇒ biết bản dịch nào phải xem lại

Khi glossary đổi (thêm/sửa/xoá thuật ngữ), hệ thống phải trả lời được **"bản dịch nào bị ảnh hưởng"**:

- `glossary_match.affected_segments(segments, old_glossary, new_glossary)` trả về **id segment** có thuật ngữ
  vừa đổi — hàm thuần, test được.
- Một bản dịch bị coi là ảnh hưởng nếu **có ít nhất một** segment như vậy.
- Sinh job **"Dịch lại · do glossary đổi"** cho các bản dịch đó, mang theo `glossary_version` mới.
- `glossary_version` là **số nguyên tăng đơn điệu**, tăng mỗi lần glossary đổi; `translations.glossary_version`
  ghi lại giá trị đã dùng lúc dịch. Đây là dấu vết duy nhất cho biết một bản dịch đã dùng glossary nào.

---

## 9. Cách test

Bài học đắt nhất của 1a: **19 task xanh test mà đường ASR vẫn chết ở hai chỗ không test nào chạm, vì chưa từng ai
chạy nó.** Vì vậy:

- **Engine giả** cho unit test luồng: alignment, retry, hạ cấp, hủy, checkpoint, QA. Những thứ này **không** cần model.
- **OPUS-MT và Qwen2.5-3B chạy thật** qua smoke script, và **một lần chạy thật phải được ghi lại bằng số**
  (số segment, thời gian, token in/out) đúng như RTF đã cứu 1a. Không có số ⇒ chưa xong.
- **Test suite không được phụ thuộc Ollama** — dùng marker, để máy khác không đỏ oan.
- Mọi test mới phải **chứng minh không rỗng** bằng mutation: sửa mã, thấy đỏ, phục hồi, verify bằng
  `git hash-object` == `git rev-parse HEAD:<path>`.
- `git status --porcelain` sạch; suite **không** được tạo thư mục `data/` thật trong repo.

---

## 10. Rủi ro

| Rủi ro | Mức | Xử lý |
|---|---|---|
| Ollama chưa cài trên máy này | **Cao** | Là việc đầu tiên của task cài đặt; nếu cài hỏng, Qwen2.5-3B không chạy thật được và phải nói thẳng, không được "xanh test" thay thế |
| `keep_alive` / cơ chế đổ model chưa đo | Trung | Đo bằng `ollama ps` **trước** khi lập plan mục 5 |
| Qwen2.5-3B trả sai số segment ở lô lớn | Trung | Chính sách §4.2, và **đếm** tỉ lệ hỏng để chọn kích thước lô |
| Migration schema hỏng DB đang có | Trung | Test dựng DB v1 rồi migrate; idempotent, có thứ tự |
| Ổ đĩa C: chỉ còn 26 GB | Thấp | `HF_HOME` phải trỏ `D:\models`; đường mặc định này **chưa từng được đi qua** ở 1a |
| Chất lượng dịch zh→vi của OPUS-MT thấp | Trung | Đây là lý do Qwen2.5 là engine chủ lực; smoke test ghi lại **cả hai** để so bằng số |

---

## 11. Tiêu chí nghiệm thu

1. Cài và **chạy thật** được OPUS-MT + Qwen2.5-3B qua Ollama; có **số đo** trong báo cáo.
2. Dịch đầu-cuối một transcript thật: `POST /api/translations` → job → bản dịch có **đủ segment, đúng thứ tự**.
3. Alignment: retry/hạ cấp/thất bại hoạt động và **đếm được**; bất biến §3 giữ.
4. Hủy giữa các lô **giữ phần đã dịch**; retry **không dịch lại từ đầu**.
5. Glossary: CRUD, nhét prompt cho Qwen, **đếm bản dịch bị ảnh hưởng** khi glossary đổi, sinh job dịch lại.
6. QA tất định ghi `qa_issues`; OPUS-MT có cờ "không đảm bảo glossary".
7. Migration v1 → v2 có test, **idempotent**, **không mất dữ liệu cũ**.
8. `GET /api/export/{translation_id}?format=&bilingual=` cho **cùng nội dung** với route cũ.
9. Suite xanh, `git status` sạch, không tạo `data/` thật trong repo.
10. Mỗi tuyên bố "xong" kèm **lệnh chính xác + dòng cuối nguyên văn**.

---

## 12. Những gì spec này KHÔNG quyết

- Kích thước lô cụ thể (đo rồi chốt).
- Ngưỡng CPS/độ dài cụ thể cho tiếng Việt (đo trên dữ liệu thật).
- Có bỏ route export cũ hay không (phase sau).
- Frontend Workspace 2 (spec UI riêng đã có).
