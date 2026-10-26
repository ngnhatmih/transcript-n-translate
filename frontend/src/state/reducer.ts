/**
 * Trạng thái CLIENT — một reducer THUẦN: không React, không DOM, không `fetch`.
 *
 * Vì sao một object PHẲNG, không lồng sâu: mọi hành động ở đây là "đổi một góc nhìn
 * của bàn làm việc" (kênh nào, đoạn nào, chế độ nào). Lồng sâu nghĩa là mỗi lần đọc
 * phải đi qua ba tầng, và mỗi lần ghi phải dựng lại ba tầng — không đổi lại được gì.
 *
 * Vì sao TÁCH khỏi React: đây là chỗ dễ "nói dối" nhất trong giao diện (đổi kênh mà
 * giữ đoạn đang phát ⇒ hiện nội dung của kênh A trong khung của kênh B — đúng lớp lỗi
 * mà Giai đoạn 2 vừa phải bịt). Tách ra thì `node:test` ghim được nó mà không cần DOM.
 *
 * `mode` là BA chế độ của spec UI §3, không phải route: shell không có router.
 */

/** BỐN chế độ làm việc. Đo lường (§4.6/§4.7) không nằm ở đây — nó là task sau.
 *
 * `dub` là chế độ THỨ TƯ, không phải một tab con của `compare`: demo đã vẽ nó thành một tab ngang
 * hàng (`mode__tab--moi` trong `_demo-long-tieng/index.html`), và nó có bố cục riêng — cột kênh,
 * dải thời gian take/chỗ, bảng dòng. Nhét nó vào `compare` là biến một màn thành hai màn chồng
 * nhau, và đo được rằng bản đầu làm thế thì một job hỏng chiếm mất chỗ của cả bản dịch.
 */
export type Mode = "edit" | "compare" | "glossary" | "dub";

export interface UiState {
  mode: Mode;
  /** Id `sources` đang chọn; `null` = chưa chọn kênh nào. */
  channelId: number | null;
  /** Chỉ số đoạn (`Segment.i`) đang phát; `null` = không phát đoạn nào. */
  currentSegment: number | null;
  playing: boolean;
  /** Đoạn đang sửa — Task 5 dùng nó để GHIM dòng khỏi bị ảo hoá tháo ra. */
  editingSegment: number | null;
  /** Bản B ghim ở chế độ Đối chiếu (`null` = chưa ghim). */
  pinnedB: number | null;
  /** Câu lỗi đang hiện; `null` = không có. */
  error: string | null;
}

export const initialState: UiState = {
  mode: "edit",
  channelId: null,
  currentSegment: null,
  playing: false,
  editingSegment: null,
  pinnedB: null,
  error: null,
};

export type Action =
  | { type: "selectChannel"; id: number }
  /**
   * BỎ CHỌN kênh — dùng khi kênh đang chọn vừa bị XOÁ.
   *
   * ⚠️ Vì sao cần một action riêng thay vì `selectChannel` một kênh khác: xoá kênh
   * đang mở thì KHÔNG có "kênh khác" nào để trỏ vào (có thể là kênh cuối cùng), và
   * để `channelId` trỏ vào một id đã chết là đúng trạng thái mà `App` phải tránh:
   * `chonTranscript(transcripts, channelId)` trả `null` nên mọi màn rơi về trạng
   * thái rỗng — nhưng danh sách `sources` vẫn còn được đọc lại, và nếu id đó được
   * cấp lại cho một kênh MỚI thì app sẽ mở nhầm kênh mà không ai bấm gì.
   *
   * `null` chính là trạng thái khởi tạo (`initialState.channelId`), tức "chưa chọn
   * kênh nào" — bỏ chọn không sinh ra một trạng thái thứ hai để mọi màn phải biết.
   */
  | { type: "clearChannel" }
  | { type: "setMode"; mode: Mode }
  | { type: "setPlaying"; playing: boolean }
  | { type: "setCurrentSegment"; i: number | null }
  | { type: "startEdit"; i: number }
  | { type: "endEdit" }
  | { type: "pinB"; id: number; aId: number }
  | { type: "setError"; error: string | null };

/**
 * Áp một hành động, trả về state MỚI. Không bao giờ sửa `state` truyền vào: React so
 * sánh THAM CHIẾU, nên sửa tại chỗ là một thay đổi mà giao diện không hề thấy.
 */
export function reduce(state: UiState, action: Action): UiState {
  switch (action.type) {
    case "selectChannel":
      // Đổi kênh thì MỌI vị trí gắn với kênh cũ phải đi theo: đoạn đang phát, trạng
      // thái phát, đoạn đang sửa, và bản B đã ghim. Giữ lại bất kỳ cái nào là hiện
      // dữ liệu của kênh A trong khung của kênh B — không có gì báo, chỉ sai.
      // `error` KHÔNG bị xoá: nó là băng-rôn dùng chung, không thuộc kênh nào.
      return {
        ...state,
        channelId: action.id,
        currentSegment: null,
        playing: false,
        editingSegment: null,
        pinnedB: null,
      };

    case "clearChannel":
      // BỎ CHỌN sau khi kênh đang mở bị XOÁ. Cùng bộ vị trí mà `selectChannel` dọn
      // (chúng đều thuộc kênh vừa biến mất), chỉ khác `channelId` là `null`.
      // Không dọn thì `currentSegment`/`editingSegment`/`pinnedB` là những chỉ số của
      // một danh sách đoạn không còn tồn tại — đúng lớp lỗi "hiện dữ liệu của kênh A
      // trong khung kênh B" mà tệp này tách khỏi React để chặn.
      return {
        ...state,
        channelId: null,
        currentSegment: null,
        playing: false,
        editingSegment: null,
        pinnedB: null,
      };

    case "setMode":
      // Đổi chế độ là đổi thứ hiện ở vùng giữa, KHÔNG phải đổi thứ đang nghe/sửa:
      // nhảy sang Đối chiếu để xem bản dịch của chính đoạn đang phát là việc thường.
      return { ...state, mode: action.mode };

    case "setPlaying":
      return { ...state, playing: action.playing };

    case "setCurrentSegment":
      return { ...state, currentSegment: action.i };

    case "startEdit":
      return { ...state, editingSegment: action.i };

    case "endEdit":
      return { ...state, editingSegment: null };

    case "pinB":
      // TỪ CHỐI ghim một hàng làm bản B khi nó ĐANG là bản A: so sánh một hàng với
      // chính nó là vô nghĩa, và hiện nó hai lần thì người đọc tin rằng có hai bản.
      // "Từ chối" ở đây nghĩa là KHÔNG ĐỔI GÌ (trả về đúng object cũ) — không âm thầm
      // bỏ ghim cũ. Nhờ vậy bất biến "pinnedB không bao giờ bằng aId" đúng quy nạp:
      // nó chỉ được đặt ở nhánh dưới, nơi `id` đã khác `aId`.
      if (action.id === action.aId) return state;
      return { ...state, pinnedB: action.id };

    case "setError":
      return { ...state, error: action.error };
  }
}
