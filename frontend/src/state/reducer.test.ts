/**
 * Test cua `reducer.ts` — HAM THUAN, nen khong can DOM: `node:test` thuong, khong
 * `jsdom`, khong Testing Library (ERRATA #5 muc 2 chi noi jsdom DUNG DUOC, khong
 * noi phai dung no o moi cho).
 *
 * Vi sao ghim ba hanh vi dau: moi cai la mot cho "noi doi" ma khong ai thay. Bai
 * "chon kenh" ghim dung loai loi Giai doan 2 vua phai bit: doi kenh ma giu doan
 * dang phat cu ⇒ hien noi dung cua kenh A trong khung cua kenh B.
 *
 * Cach chay: `npm test` (TOAN BO). KHONG loc bang tham so: script `test` co glob
 * nen tham so thua bi noi vao va runner nhan mot duong dan khong ton tai. Loc
 * theo TIEU DE bai, va dung lay mot con so tuyet doi lam dau hieu (ERRATA #6 muc 3).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { initialState, reduce } from "./reducer.ts";
import type { UiState } from "./reducer.ts";

describe("reducer trang thai client", () => {
  it("chon kenh thi dat kenh do va xoa doan dang phat", () => {
    // Doi kenh ma giu doan dang phat cu la hien thi noi dung cua kenh A trong
    // khung cua kenh B — dung loai "noi doi" ma giai doan 2 vua phai bit.
    const s = reduce(
      { ...initialState, channelId: 1, currentSegment: 9 },
      { type: "selectChannel", id: 2 },
    );
    assert.equal(s.channelId, 2);
    assert.equal(s.currentSegment, null);
  });

  it("chon kenh thi xoa luon doan dang sua va ghim B (chung thuoc kenh CU)", () => {
    const truoc: UiState = {
      ...initialState,
      channelId: 1,
      currentSegment: 9,
      playing: true,
      editingSegment: 9,
      pinnedB: 4,
    };
    const s = reduce(truoc, { type: "selectChannel", id: 2 });
    assert.equal(s.channelId, 2);
    assert.equal(s.playing, false);
    assert.equal(s.editingSegment, null);
    assert.equal(s.pinnedB, null);
  });

  it("doi mode thi giu kenh va doan dang phat", () => {
    const s = reduce(
      { ...initialState, channelId: 1, currentSegment: 9 },
      { type: "setMode", mode: "compare" },
    );
    assert.equal(s.mode, "compare");
    assert.equal(s.channelId, 1);
    assert.equal(s.currentSegment, 9);
  });

  it("XOA KENH DANG CHON: `clearChannel` dua channelId ve null va don CUNG bo vi tri nhu `selectChannel`", () => {
    // ⚠️ Vì sao là một ACTION riêng chứ không phải `selectChannel(kenhKhac)`: xoá kênh đang
    // mở thì không có "kênh khác" nào để trỏ vào (có thể là kênh cuối cùng). Để `channelId`
    // ở lại một id ĐÃ CHẾT là trạng thái mà `App` phải tránh: `chonTranscript` trả `null` nên
    // màn rơi về trạng thái rỗng, nhưng id trần đó vẫn sống trong state và có thể được cấp
    // lại cho một kênh khác ở lần đọc sau — khi đó app tự mở nhầm kênh mà không ai bấm gì.
    const truoc: UiState = {
      ...initialState,
      channelId: 1,
      currentSegment: 9,
      playing: true,
      editingSegment: 9,
      pinnedB: 4,
      // `error` là băng-rôn DÙNG CHUNG, không thuộc kênh nào ⇒ KHÔNG được xoá (cùng luật với
      // `selectChannel`, xem comment ở đó).
      error: "khong doc duoc kenh",
    };
    const s = reduce(truoc, { type: "clearChannel" });
    assert.equal(s.channelId, null, "bỏ chọn ⇒ `null`, đúng trạng thái `initialState`");
    assert.equal(s.currentSegment, null);
    assert.equal(s.playing, false);
    assert.equal(s.editingSegment, null);
    assert.equal(s.pinnedB, null);
    assert.equal(s.error, "khong doc duoc kenh", "`error` không thuộc kênh nào");
    assert.notEqual(s, truoc, "phải trả về object MỚI (React so sánh tham chiếu)");
  });

  it("`clearChannel` trên state CHUA chon kenh la no-op VE Y NGHIA (van la null, khong nem)", () => {
    // Idempotent: một lần bấm xoá thứ hai (hoặc một kênh không được chọn) không được làm
    // reducer ném — nó chỉ giữ nguyên câu trả lời "chưa chọn kênh nào".
    const s = reduce({ ...initialState }, { type: "clearChannel" });
    assert.equal(s.channelId, null);
    assert.equal(s.currentSegment, null);
  });

  it("khong cho ghim ban B trung ban A", () => {
    const s = reduce(
      { ...initialState, pinnedB: null },
      { type: "pinB", id: 3, aId: 3 },
    );
    assert.equal(s.pinnedB, null);
  });

  it("ghim B trung A bi TU CHOI: state tra ve NGUYEN TRANG, ke ca ghim cu", () => {
    const truoc: UiState = { ...initialState, channelId: 1, pinnedB: 4 };
    const s = reduce(truoc, { type: "pinB", id: 3, aId: 3 });
    // "Tu choi" nghia la KHONG doi gi — khong am tham bo ghim cu, cung khong am
    // tham ghim cai vua bi tu choi. Bat bien "pinnedB khong bao gio bang aId" van
    // dung vi no chi dat duoc qua nhanh duoi day.
    assert.equal(s, truoc);
  });

  it("ghim B khac A thi ghim that", () => {
    const s = reduce(
      { ...initialState, channelId: 1, pinnedB: 4 },
      { type: "pinB", id: 5, aId: 3 },
    );
    assert.equal(s.pinnedB, 5);
  });

  it("setPlaying/setCurrentSegment/startEdit/endEdit/setError chi doi dung mot truong", () => {
    const s0: UiState = { ...initialState, channelId: 1, currentSegment: 2 };

    const phat = reduce(s0, { type: "setPlaying", playing: true });
    assert.equal(phat.playing, true);
    assert.equal(phat.currentSegment, 2);

    const nhay = reduce(s0, { type: "setCurrentSegment", i: 7 });
    assert.equal(nhay.currentSegment, 7);
    assert.equal(nhay.channelId, 1);

    const sua = reduce(s0, { type: "startEdit", i: 7 });
    assert.equal(sua.editingSegment, 7);
    assert.equal(sua.currentSegment, 2);

    const thoiSua = reduce(sua, { type: "endEdit" });
    assert.equal(thoiSua.editingSegment, null);
    assert.equal(thoiSua.currentSegment, 2);

    const loi = reduce(s0, { type: "setError", error: "khong doc duoc kenh" });
    assert.equal(loi.error, "khong doc duoc kenh");
    assert.equal(reduce(loi, { type: "setError", error: null }).error, null);
  });

  it("reduce KHONG sua state goc (ham thuan)", () => {
    const truoc: UiState = { ...initialState, channelId: 1, currentSegment: 9 };
    const banSao: UiState = { ...truoc };
    const s = reduce(truoc, { type: "selectChannel", id: 2 });
    assert.notEqual(s, truoc, "phai tra ve object MOI");
    assert.deepEqual(truoc, banSao, "state goc bi sua ⇒ React se khong thay doi");
  });

  it("initialState la MOT object PHANG (khong long sau)", () => {
    for (const [khoa, giaTri] of Object.entries(initialState)) {
      const kieu = typeof giaTri;
      assert.ok(
        kieu === "string" || kieu === "number" || kieu === "boolean" || giaTri === null,
        `truong ${khoa} phai la gia tri phang, do duoc ${kieu}`,
      );
    }
  });
});
