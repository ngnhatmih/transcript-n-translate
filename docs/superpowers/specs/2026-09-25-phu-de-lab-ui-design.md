# phu-de-lab — Thiết kế UI/UX

**Ngày:** 2026-09-25
**Trạng thái:** Chờ người dùng duyệt
**Quan hệ với spec khác:** đây là file thiết kế **giao diện**, tách riêng khỏi
`2026-09-25-phu-de-lab-design.md` (spec kiến trúc). Những chỗ file này buộc spec kiến trúc
phải đổi được liệt kê ở §11.

---

## 0. Vì sao có file riêng

Spec kiến trúc quyết định *hệ thống làm gì*. File này quyết định *người dùng nhìn thấy gì và
thao tác thế nào*. Khi soi lại 10 tính năng của spec v2 qua lăng kính UI, phát hiện ra ba lỗ
làm thay đổi cả bố cục lẫn backend — nên không thể chỉ là một mục nhỏ trong spec kiến trúc.

---

## 1. Hướng thẩm mỹ

**Tên:** *Control Room* — công nghiệp thực dụng (industrial utilitarian).

**Neo nhận diện:** **thời gian là trục dọc.** Một thanh timecode chạy suốt chiều cao, mỗi đoạn
phụ đề là một khối dài tỉ lệ với thời lượng thật, và một đầu đọc amber chạy dọc theo nó.
Cắt logo đi vẫn nhận ra ngay đây là app gì.

**Nguồn cảm hứng (khái niệm, không sao chép hình ảnh):** bàn trộn âm thanh, máy ghi Nagra,
trạm kiểm phụ đề của đài truyền hình. Cụ thể là *thiết bị rack trong phòng điều khiển lờ mờ*:
mặt kim loại sơn nhám, nhãn khắc chìm, và đúng một ngọn đèn có nghĩa.

### DFII

| Tiêu chí | Điểm | Lý do |
|---|---|---|
| Aesthetic Impact | 5 | Ngôn ngữ thiết bị đo lường; không giống app phụ đề nào |
| Context Fit | 5 | Bàn làm việc mật độ cao dùng hàng giờ; timecode là dữ liệu trung tâm |
| Implementation Feasibility | 5 | CSS Grid + biến CSS + hai font; không cần WebGL |
| Performance Safety | 4 | Danh sách ảo hoá; không blur/shadow nặng; trừ 1 vì grain phủ toàn trang |
| **Consistency Risk** | 2 | Một hệ token, một quy tắc màu, rủi ro thấp |

**DFII = (5+5+5+4) − 2 = 17 → chặn trần 15.** Mức "Excellent — execute fully".

### Hướng đã loại và lý do

| Hướng | Vì sao loại |
|---|---|
| Dark + neon + glassmorphism ("AI dashboard") | Đúng cái bẫy trope. Và nó không nói lên điều gì về việc *đây là phòng biên tập phụ đề* |
| Editorial sáng, serif, hai cột như sách | Tuyệt cho việc dịch và soát, nhưng không nhét được bảng hàng đợi, tiến trình, benchmark vào cùng một ngôn ngữ hình ảnh |
| TUI thuần (không card, không bo góc) | Rất đáng nhớ nhưng dễ thành xấu nếu kém tay, và khó cho người dùng không kỹ thuật |

Hướng editorial **không bị vứt đi**: *cấu trúc* đường gáy của nó được mượn cho chế độ Đối chiếu
(§4.3), nhưng vẫn nói ngôn ngữ thị giác của Control Room. Đây là mượn bố cục, không phải trộn
hai thẩm mỹ — vẫn nằm trong giới hạn "tối đa hai hướng" của quy tắc thiết kế.

---

## 2. Hệ thống thiết kế

### 2.1 Chữ

| Vai trò | Font | Vì sao |
|---|---|---|
| Tiêu đề, nhãn khắc | **Archivo Expanded** (trục `wdth`) | Grotesque của Omnibus-Type, khẩu độ hẹp. Nhãn giãn rộng đọc như khắc chìm trên mặt máy, không phải heading web |
| Nội dung, giao diện | **Archivo** | Cùng hệ, giữ một giọng duy nhất. Không phải Inter/Roboto/system |
| Số liệu, timecode | **IBM Plex Mono** | Số thẳng cột. Đây là **mặt đồng hồ đo**, làm việc thật: timecode và CPS phải xếp thẳng hàng dọc |

Thang cỡ chữ: `9.5px` nhãn mono · `10.5px` số liệu phụ · `11.5px` phụ chú · `12.5px` giao diện ·
`13.5px` dòng phụ đề trong chế độ mật độ cao · `15–16px` phụ đề trong chế độ đọc.

> **Ràng buộc cứng:** app phải chạy **hoàn toàn offline** (spec kiến trúc §17.8), nên **không
> được nạp font từ Google Fonts CDN**. Cả ba mặt chữ phải **self-host woff2** ở
> `frontend/public/fonts/` và khai báo bằng `@font-face`. Bản mockup dùng CDN chỉ vì nó là
> mockup; bản thật thì không.

### 2.2 Màu

```css
:root{
  /* nền — graphite ẤM, không phải đen xanh */
  --panel-0:#12110F;   /* nền app */
  --panel-1:#1A1917;   /* mặt panel */
  --panel-2:#232220;   /* mặt nổi */
  --panel-3:#2B2A27;   /* rãnh, track */

  /* chữ — trắng ngà ấm, như sơn khắc */
  --ink-0:#E8E4DC;
  --ink-1:#9A948A;
  --ink-2:#6B665C;

  --rule:#34322E;      /* đường kẻ 1px */
  --signal:#FFB020;    /* HIỆU ỨNG DUY NHẤT — đèn báo amber */
  --fault:#B4443C;     /* CHỈ dùng cho lỗi thật và vân "nghi ngờ" */
  --ok:#7E8C6A;        /* xác nhận, dùng rất tiết chế */
}
```

**Graphite ấm thay vì đen xanh** vì đen-xanh là màu mặc định của dark-mode SaaS; ấm thì đọc ra
kim loại sơn. Tương phản `--ink-0` trên `--panel-0` ≈ **14:1**, vượt AA thoải mái.

**Quy tắc màu (bắt buộc, không thương lượng):**

1. **Amber chỉ có một nghĩa: đang hoạt động / cần chú ý.** Không dùng amber trang trí.
2. **Đoạn nghi ngờ mã hoá bằng VÂN, không bằng màu** — xem §2.5.
3. `--fault` chỉ cho trạng thái lỗi thật. Không dùng cho "cảnh báo nhẹ".
4. Thành công hiển thị bằng **ký tự** (`✓`) làm tín hiệu chính. `--ok` chỉ là màu chữ/viền phụ
   trợ cho chip "đã duyệt", **không** phải một accent thứ ba cạnh tranh với amber: nó là ô-liu
   bão hoà thấp, không bao giờ dùng cho khối lớn hay trạng thái "đang chạy".

### 2.3 Không gian

- **Bất đối xứng có chủ ý:** ba cột `214px / flex / 286px`. Không bao giờ chia đều.
- **Rail thời gian 72px cố định**, không cuộn ngang, không co giãn.
- Nhịp dọc: hàng `32px` (một dòng) hoặc `44px` (hai dòng, mặc định). Người dùng chọn mật độ.
- **Bo góc 2px.** Không phải 0 — 0 trông như lỗi render; 2px đọc ra "đã gia công".
- Không shadow mềm. Phân tầng bằng **đường kẻ 1px** + chênh lệch độ sáng nền 4–6%.

### 2.4 Bề mặt

Phủ **grain 2,8%** (nhiễu SVG `feTurbulence`) toàn trang, `pointer-events:none`. Gợi màn hình
CRT và giấy can. Đủ nhẹ để không hại tương phản. Tắt khi `prefers-reduced-transparency`.

### 2.5 Quyết định: "nghi ngờ" là vân, không phải màu

Đoạn bị đánh dấu `suspect` (từ `avg_logprob` / `no_speech_prob`, spec kiến trúc §8.4) **không**
tô nền đỏ. Nó được đánh bằng **vân chéo 45° ở lề trái, rộng 6px**.

Lý do, theo thứ tự quan trọng:

1. Giữ amber là tài nguyên duy nhất có nghĩa — không đem chia cho một loại cảnh báo nữa.
2. **An toàn cho người mù màu.** Đỏ/xanh là cặp tệ nhất; vân thì không phụ thuộc màu nào cả.
3. Vân đọc được ở mật độ cao, nơi màu bị nhiễu và mắt đã mỏi.

### 2.6 Chuyển động

**Một chuỗi vào duy nhất:** khi job bắt đầu, **thanh timecode rail sáng dần từ trên xuống**
theo tiến độ thật. Chuyển động mang nghĩa (tiến độ), không trang trí.

- Hover: **đường kẻ lề trái dày lên**, không đổi nền.
- Transition `120ms ease-out`. Không bounce, không spring, không parallax.
- `prefers-reduced-motion: reduce` → tắt sweep, thay bằng số tiến độ dạng chữ.
- Ngoài hai thứ trên, **chỉ còn transition `120ms` cho hover/focus**. Không micro-animation rải
  rác, không parallax, không shimmer. Tổng số chuyển động *có chủ đích* trong app: **hai**.

---

## 3. Kiến trúc thông tin — ba vùng, không phải hai pane

Spec kiến trúc v1–v2 vẽ hai pane chia đôi. Bố cục đó **không chịu được** hai thứ mà chính spec
đã yêu cầu: nhiều source cùng lúc (P1 gom lô theo giai đoạn chỉ có nghĩa khi có nhiều job) và
việc nghe lại để soát.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ PHÒNG THU BIÊN TẬP    [● Ollama]  [▮▮▮▯▯ 3.2/8GB]  [GĐ: ASR·turbo]       [⚙]  │
├──────────────┬────────────────────────────────────────┬───────────────────────┤
│ KÊNH         │  BÀN LÀM VIỆC                          │  HÀNG ĐỢI             │
│ (214px)      │  (flex)                                │  (286px)              │
│              │  ┌─rail─┬─────────────────────────────┐│                       │
│ ● video-01   │  │ 0:01 │ …                           ││  ▸ ASR·turbo   ▓▓▓░░  │
│ ○ video-02   │  │ 0:12╱│ [nghi ngờ]                  ││  ⏸ MT·qwen2.5-7b      │
│ ○ video-03   │  └──────┴─────────────────────────────┘│    chờ gom lô         │
│ [+ NẠP LIỆU ]│  [ BIÊN TẬP │ ĐỐI CHIẾU │ THUẬT NGỮ ]   │                       │
├──────────────┴────────────────────────────────────────┴───────────────────────┤
│ ▶ 0:15/12:04  [━━━━━━━━━░░░░░░]  ETA 4m           [SRT] [VTT] [ASS]           │
└───────────────────────────────────────────────────────────────────────────────┘
```

| Vùng | Trả lời câu hỏi | Giải quyết |
|---|---|---|
| **KÊNH** | "Tôi đang có những tệp nào, cái nào xong bước nào?" | U1 |
| **BÀN LÀM VIỆC** | "Nội dung ra sao, sửa ở đâu?" | U3, U6, U7 |
| **HÀNG ĐỢI** | "Cái gì đang chạy, cái gì chờ, **vì sao chờ**?" | U2 |
| **TRANSPORT** | "Nghe thử, tua, chỉnh mốc, xuất" | U5 |

Mọi màn hình làm việc đều nằm trong khung này. Không có điều hướng trang, không có route riêng
cho từng bước — đây là một bàn làm việc, không phải một luồng wizard.

**Hai ngoại lệ có chủ ý**, và header + thanh transport vẫn giữ nguyên ở cả hai:

- **Chế độ Đối chiếu** thay ruột vùng BÀN LÀM VIỆC (hai cột + CPS), vẫn giữ KÊNH và HÀNG ĐỢI.
- **Hai màn hình đo lường** (§4.6 bảng eval, §4.7 chấm tay) **thay toàn bộ vùng giữa**: chúng
  không gắn với một kênh cụ thể nào, nên KÊNH và HÀNG ĐỢI bị ẩn đi. Đây là chế độ *đo*, không
  phải chế độ *làm*.

---

## 4. Tám màn hình

### 4.1 · Màn hình chính — chế độ BIÊN TẬP

Rail thời gian + danh sách đoạn. Đoạn đang phát có lề trái amber và đầu đọc chạy dọc rail.
Đoạn nghi ngờ có vân chéo ở lề kèm nhãn lý do (`nhạc nền`, `nghi ngờ`).

Thanh transport ở đáy: nút phát, timecode mono `0:04.12 / 12:04.30`, track có đầu đọc, ETA, và
ba nút xuất.

### 4.2 · Chế độ BIÊN TẬP — trạng thái rỗng

Vùng giữa là khung kẻ nét đứt với chữ **Archivo Expanded giãn rộng**:
`KÉO TỆP VÀO ĐÂY` + dòng mono liệt kê định dạng nhận được. Không phải một thẻ nhỏ giữa màn hình.

### 4.3 · Chế độ ĐỐI CHIẾU

```
 ┌─rail─┬─────────────────────┬─────────────────────────┬──────────┐
 │ 0:01 │ 大家好               │ Chào mọi người          │    14    │
 │ 0:04 │ 今天我们来说…        │ Hôm nay chúng ta bàn…   │  21 ⚠    │
 └──────┴─────────────────────┴─────────────────────────┴──────────┘
                     ↑ đường gáy 1px
```

Cột gốc (mờ hơn) | cột dịch (sáng) | **cột CPS**. Dòng vượt ngưỡng đọc có `⚠` màu amber.

**Vì sao cột CPS quan trọng:** tiếng Việt dài gấp 2–3× tiếng Trung. Dòng dịch vượt ngưỡng đọc
là lỗi phụ đề phổ biến nhất, và nó **chỉ lộ ra khi đặt hai thứ cạnh nhau**. Đây là lý do tồn
tại của cả chế độ này.

Bộ chọn bản dịch là **segmented control mono**, không phải tab nổi — 4 engine × nhiều phiên bản
prompt sẽ làm tab nổ tung. Cần so hai bản thì bấm **ghim bản B** để hiện cột thứ ba.

### 4.4 · Tab THUẬT NGỮ

Bảng 5 cột: `Nguồn zh | Bản dịch vi | Loại | Trạng thái | Ảnh hưởng`.

Thanh trên: `5 thuật ngữ · 4 đã duyệt` + `⚠ đổi glossary → 2 bản dịch bị đánh dấu lỗi thời`.

Hàng chờ duyệt có lề trái amber. Hàng chưa có bản dịch có chip `✕ trống` màu lỗi.

Khối dưới: **thuật ngữ đang chọn xuất hiện ở đâu** — liệt kê mốc thời gian theo từng kênh, kèm
cảnh báo `⚠ 2 dòng trong kênh 01 chưa chứa thuật ngữ này`.

**Vì sao có cột "Ảnh hưởng":** sửa một thuật ngữ không phải sửa một ô — nó làm hỏng 12 dòng đã
dịch. Cột này biến `glossary_version` ở spec kiến trúc thành thứ **nhìn thấy được**, và hàng đợi
tự sinh job *"Dịch lại · kênh 01 · do glossary đổi"*.

### 4.5 · Chế độ CHIMERA

Bật bằng chip amber trên thanh công cụ. Dải cảnh báo chéo chạy ngang:

> `◆ CHẾ ĐỘ CHIMERA · 7 lượt gọi model cho mỗi lô · chậm ~7× · VRAM không tăng (chạy tuần tự)`

Mỗi dòng đã xử lý được **mở rộng**: bản hợp nhất ở trên (đánh `◆`, kèm `HỢP NHẤT TỪ 6 ỨNG VIÊN ·
hyp 3 · 1.4s`), và 6 ứng viên xếp chồng bên dưới, ứng viên được chọn sáng hơn.

**Vì sao cho thấy cả 6 ứng viên:** một chế độ tốn gấp 7 lần phải biện minh cho chi phí của nó.
Nếu chỉ hiện bản cuối thì không ai biết nó khác gì chế độ thường, và sẽ không ai dùng.

Hàng đợi ghi thẳng chi phí: `ETA toàn kênh 01 ≈ 31 phút — gấp ~7 lần bình thường`.

### 4.6 · Chấm điểm — bảng kết quả eval

Bảng WER: `Engine × 5 clip × WER TB`. Mỗi ô có thanh tỉ lệ nhỏ + phần trăm mono.

- Hàng tốt nhất có `◆` amber ở đầu.
- Ô tệ nhất trong hàng tô `--fault` (chỉ ô tệ nhất, không tô cả hàng).
- Dải benchmark bên dưới: `RTF · RTF · thời gian nạp model · hệ số token`.

**Cột "5 · có hát" cố tình xấu ở cả ba engine.** Đó là sự thật: ASR trên audio có hát là trường
hợp sinh rác nhiều nhất. Một bảng eval mà mọi cột đều đẹp là bảng eval vô dụng.

Dòng `Hệ số token: 1.0 → hiệu chỉnh 1.34` chính là con số mà spec kiến trúc §8.7.1 ghi
`PHẢI ĐO`. Màn hình này là nơi nó được hiệu chỉnh và hiển thị, để lần sau không ai đoán lại.

### 4.7 · Chấm tay 20 câu

Một câu một lần, giữa màn hình. Trên: `câu 7 / 20 · engine · prompt v1`. Khung gốc (zh) rồi
khung dịch (vi). Dưới: năm phím `1 2 3 4 5` với nhãn `SAI / KÉM / ĐƯỢC / TỐT / SÁT`.

Bấm phím số để chấm, `←` quay lại câu trước, `Esc` thoát. Kết quả ghi vào `eval/report.md`.

**Vì sao chấm tay mà không dùng BLEU/COMET:** không có bản tham chiếu đủ tin cho phụ đề
Trung→Việt. Đo bằng thứ mình thật sự có, thay vì đo bằng một chỉ số nghe có vẻ khoa học.

### 4.8 · Trạng thái lỗi — Ollama chưa bật

Dải vằn chéo `--fault` chạy ngang **đỉnh** cửa sổ (không phải toast). Header đổi pill thành
`Ollama mất kết nối` với chấm đỏ. Vùng giữa:

> **Không kết nối được Ollama**
> Bóc băng vẫn chạy được, nhưng **mọi engine dịch đều cần Ollama**.
> Mở terminal và chạy `ollama serve`, rồi bấm thử lại. → `[ Thử lại ]`

**Vì sao là trạng thái hạng nhất:** đây là lỗi phổ biến nhất của một app local, và app **không
dùng được** nếu thiếu. Một toast bay qua rồi biến mất là thiết kế sai.

---

## 5. Mô hình tương tác

### 5.1 Bàn phím — đây là công cụ, không phải trang web

Người dùng sẽ ngồi với app này hàng giờ. Không có bàn phím thì nó không phải công cụ.

| Phím | Việc | | Phím | Việc |
|---|---|---|---|---|
| `Space` | phát / dừng | | `[` `]` | đặt mốc start/end tại đầu đọc |
| `J` / `K` | dòng trước / dòng sau | | `S` | tách dòng tại đầu đọc |
| `Enter` | sửa dòng đang chọn | | `M` | gộp với dòng dưới |
| `Esc` | thoát sửa | | `N` | nhảy tới đoạn nghi ngờ kế tiếp |
| `Shift+←/→` | nudge mốc thời gian ±0,1s | | `Ctrl+1/2/3` | Biên tập / Đối chiếu / Thuật ngữ |
| `Alt+←/→` | nudge ±1s | | `Ctrl+Enter` | chạy job cho kênh đang chọn |

Trong màn hình chấm tay: `1`–`5` chấm, `←` lùi, `Esc` thoát.

### 5.2 Sửa chữ và mốc thời gian

- Click dòng (hoặc `Enter`) → ô sửa tại chỗ, con trỏ ở cuối.
- Sửa xong `Enter` lưu, `Esc` huỷ. **Nếu có thay đổi chưa lưu, `Esc` hỏi lại.**
- Nudge mốc bằng `Shift/Alt + ←/→`; mỗi lần nudge phát lại 300ms quanh mốc mới để nghe ngay.
- `[` và `]` đặt mốc tại vị trí đầu đọc — nhanh hơn kéo chuột rất nhiều.
- Mọi thay đổi làm `transcripts.version` tăng → bản dịch cũ thành `stale` (spec kiến trúc §5.3).

### 5.3 Ảo hoá và focus

Danh sách ảo hoá unmount dòng ngoài viewport. **Dòng đang sửa được GHIM** — không bị unmount dù
cuộn đi đâu. Bản nháp của ô đang sửa giữ trong state, không phải trong DOM.

### 5.4 Tiến độ — hai thanh, không trộn

| Thanh | Đơn vị |
|---|---|
| Công đoạn | `%` khi tải (yt-dlp) · giây khi extract (ffmpeg) · phút audio khi ASR · số lô khi dịch |
| Tổng thể | ước tính từ RTF đo được (bảng benchmark) |

Trộn hai thứ này thành một thanh là nguyên nhân kinh điển của thanh tiến độ nhảy loạn.

`ffmpeg` không báo tiến độ theo `%` — hiển thị theo giây đã xử lý, đừng giả vờ có phần trăm.

---

## 6. Thành phần dùng lại

| Thành phần | Nhiệm vụ | Dùng ở |
|---|---|---|
| `AppShell` | khung ba vùng + header + transport | mọi màn hình |
| `ChannelList` | danh sách kênh + đèn trạng thái hai bước | 4.1, 4.3, 4.4, 4.5 |
| `TimeRail` | cột timecode mono cố định 72px | 4.1, 4.3, 4.5 |
| `SegmentRow` | một đoạn: rail + chữ + nhãn + vân nghi ngờ | 4.1, 4.5 |
| `CompareRow` | gốc / dịch / CPS | 4.3 |
| `QueuePanel` | job + thanh tiến độ + **lý do chờ** | mọi màn hình |
| `TransportBar` | phát, timecode, track, ETA, xuất | mọi màn hình |
| `ModeSwitch` | segmented control ba chế độ | 4.1, 4.3, 4.4 |
| `StatusPill` | Ollama / VRAM / giai đoạn | mọi màn hình |
| `FaultStrip` | dải vằn chéo lỗi | 4.8 |
| `ScoreKeys` | thang 1–5 | 4.7 |
| `MeterBar` | thanh tỉ lệ nhỏ | 4.6 |

Dùng **Radix / shadcn cho hành vi** — dialog, dropdown, tab, quản lý focus, ARIA — vì đó là thứ
rất khó tự viết đúng. **Toàn bộ phần nhìn viết từ token ở §2.** shadcn vốn là mã copy vào repo
nên restyle hoàn toàn được; dùng nguyên giao diện mặc định của nó là thất bại.

---

## 7. Khả năng tiếp cận

| Mục | Cách làm |
|---|---|
| Tương phản | `--ink-0` / `--panel-0` ≈ 14:1; `--ink-1` / `--panel-1` ≈ 5,4:1 |
| Không phụ thuộc màu | Nghi ngờ = vân · trạng thái kênh = chữ (`✓`, `▓▓░`, `chờ`) · xong = `✓` |
| Bàn phím | Mọi hành động đều có phím tắt; focus ring 2px `--signal`, không bao giờ `outline:none` |
| Đọc màn hình | `aria-live` cho trạng thái job; vùng hàng đợi là `role="status"` |
| Chuyển động | `prefers-reduced-motion` tắt sweep; `prefers-reduced-transparency` tắt grain |
| Cỡ chữ | Không nhỏ hơn 9,5px (chỉ cho nhãn mono in hoa); nội dung ≥ 12,5px |

---

## 8. Ràng buộc kỹ thuật riêng của giao diện

1. **Font self-host, không CDN** — vì app chạy offline.
2. **Ảo hoá danh sách** — transcript 2 giờ ≈ 2000 dòng.
3. **Dòng đang sửa được ghim** — chống mất focus do ảo hoá.
4. **Media cần HTTP range request** — player phải seek được; backend cần endpoint serve media
   hỗ trợ `Range` (spec kiến trúc chưa có, xem §11).
5. **CPS tính ở đâu** — công thức CPS thuần, phải nằm trong `domain/` để test được không cần model.
6. **Grain phủ toàn trang** — dùng `pointer-events:none` và một lớp duy nhất, không lặp lại
   trong từng component.

---

## 9. Truy vết — mười phát hiện UI và chỗ giải quyết

| Mã | Phát hiện | Giải quyết ở |
|---|---|---|
| U1 | Không có chỗ cho nhiều source | §3 vùng KÊNH |
| U2 | Job bị đẩy ra sau mà không thấy hàng đợi | §3 vùng HÀNG ĐỢI, §4.1 lý do chờ |
| U3 | Việt dài gấp 2–3× Trung, hai pane tách rời | §4.3 chế độ Đối chiếu + CPS |
| U4 | Chỉnh timestamp bằng chuột là cực hình | §5.1 `[` `]`, §5.2 nudge + nghe lại |
| U5 | Không có player → `suspect` vô dụng | §3 TRANSPORT, §8.4 range request |
| U6 | Ảo hoá + sửa trực tiếp = mất focus | §5.3 ghim dòng |
| U7 | N bản dịch dạng tab sẽ nổ | §4.3 segmented + ghim bản B |
| U8 | Trạng thái rỗng/lỗi chưa thiết kế | §4.2, §4.8 |
| U9 | Tiến độ không đồng nhất | §5.4 hai thanh |
| U10 | Không có bàn phím | §5.1 |

---

## 10. Không làm (YAGNI)

1. **Sáng/tối chuyển đổi được.** Chỉ có một chế độ tối — đó là bản sắc, không phải tuỳ chọn.
2. **Tuỳ biến bảng màu.** Một bảng, có kỷ luật.
3. **Animation trang trí, skeleton shimmer, confetti.**
4. **Layout responsive cho điện thoại.** Đây là bàn làm việc mật độ cao; dưới 1100px chỉ cần
   không vỡ, không cần dùng được.
5. **Wizard nhiều bước.** Một bàn làm việc, không phải luồng cài đặt.
6. **Kéo-thả sắp xếp lại cột.** Không có nhu cầu, và nó phá tính ổn định của bố cục.

---

## 11. Những gì spec kiến trúc phải đổi theo file này

Đây là phần "tổng" — danh sách thay đổi cần áp vào `2026-09-25-phu-de-lab-design.md`:

| # | Spec kiến trúc đang nói | Phải thành |
|---|---|---|
| 1 | §9 vẽ hai pane chia đôi | **Ba vùng**: KÊNH / BÀN LÀM VIỆC / HÀNG ĐỢI + thanh transport |
| 2 | Không có trình phát media | Thêm **endpoint serve media có HTTP `Range`** và thanh transport |
| 3 | §11 API không có media | Thêm `GET /api/media/{source_id}` hỗ trợ `Range` |
| 4 | Không nói gì về bàn phím | Thêm **bảng phím tắt** như một yêu cầu, không phải điểm cộng |
| 5 | Không nói gì về font | Thêm ràng buộc **font self-host woff2, không CDN** (vì offline) |
| 6 | Không có CPS | Thêm **tính CPS trong `domain/`** + cảnh báo ngưỡng |
| 7 | Không có UI glossary ảnh hưởng | Ghi rõ: đổi glossary → hiện **số bản dịch bị ảnh hưởng** + job dịch lại |
| 8 | Không có UI eval | Ghi rõ `backend/eval/` có **hai màn hình**: bảng kết quả và chấm tay |
| 9 | Không có UI Chimera | Ghi rõ Chimera hiện **6 ứng viên + bản hợp nhất** và **cảnh báo chi phí** |
| 10 | §9 "N bản dịch dạng tab" | Đổi thành **segmented control + ghim bản B** |
| 11 | Không có trạng thái lỗi | Ghi rõ **Ollama mất kết nối là trạng thái hạng nhất** |

---

## 12. Tiêu chí thành công của giao diện

1. Nhìn ảnh chụp không có logo vẫn nhận ra: **đây là app mà thời gian là trục dọc**.
2. Nạp 3 tệp cùng lúc → thấy rõ tệp nào đang chạy, tệp nào chờ, **và vì sao chờ**.
3. Sửa một thuật ngữ → thấy ngay **bao nhiêu bản dịch bị ảnh hưởng** trước khi bấm lưu.
4. Ở chế độ Đối chiếu, phát hiện được **dòng dịch vượt ngưỡng đọc** mà không phải tự đếm.
5. Không chạm chuột lần nào vẫn làm được **toàn bộ phần biên tập**: bóc băng → soát → sửa dòng →
   nudge mốc → dịch → xuất. *(Thao tác nạp tệp ban đầu vẫn cần chuột hoặc dán liên kết — đó là
   giới hạn của trình duyệt, không phải của thiết kế.)*
6. Tắt Ollama → app nói rõ **cái gì còn chạy được, cái gì không**, và cách sửa.
7. Bảng eval trả lời được "engine nào tốt hơn" bằng **số**, không bằng cảm giác.
