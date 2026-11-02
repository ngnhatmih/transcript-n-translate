/**
 * Test `studio.ts` — tầng DẪN XUẤT thuần của bàn làm việc.
 *
 * Vì sao tệp này tồn tại: đo bằng `Select-String` trên 8 tệp test cũ, KHÔNG bài nào
 * chạm một hàm nào của `studio.ts`. Đó là tầng quyết định "dòng nào có việc", "bước
 * nào bị chặn", "chữ nào là bản dịch" — sai ở đây thì giao diện nói dối, mà `tsc`
 * vẫn xanh vì kiểu không sai.
 *
 * Runner: `node --test` + loader SWC (`test/swc-loader.mjs`). Import PHẢI kèm đuôi
 * `.ts` (loader chỉ chặn `file:` kết thúc `.ts`/`.tsx`). Alias `@/` KHÔNG dùng được ở
 * đây: `package.json` không có `imports` map, nên tệp này nhập `../api/types.ts`.
 *
 * Ba luật của repo được GHIM thành bài, vì chúng từng bị vi phạm:
 *   1. `null` KHÁC `0` — "chưa đo được" không phải "đo ra 0".
 *   2. Số của máy chủ là nguồn sự thật — không tự tính lại CPS, không tự chia nén
 *      khi máy chủ đã gửi `need`.
 *   3. Duyệt rồi thì hết việc — cùng luật với `issuesFor` của bản đã duyệt.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type {
  DubPlanRow,
  Job,
  Segment,
  Status,
  Transcript,
  TranslationCps,
  TranslationDetail,
} from "../api/types.ts";
import {
  bangBanDich,
  bangCps,
  chuCuaDoan,
  doDai,
  dongMayChu,
  dungDong,
  duongOng,
  hangDoi,
  lyDoChuaXuatDuoc,
  NGUONG_NEN,
  raSrt,
  soVi,
  tachTuKhac,
  tiLeNen,
  viecCuaBanGhi,
  viecCuaDong,
  viecCuaDongList,
  viecCuaDoan,
  type DauVaoDuongOng,
  uocLuongTienDo,
  chuConLai,
  trungViThoiGianChay,
  lopCua,
  mauLop,
  moTaLop,
  NHAN_LOP,
} from "./studio.ts";

// ---------------------------------------------------------------------------
// Dung du lieu thu — chi nhung truong ma ham doc, khong bia them.
// ---------------------------------------------------------------------------

function doan(p: Partial<Segment> & { i: number }): Segment {
  return { start: 0, end: 1, text: "", suspect: false, ...p };
}

function banGhi(segments: Segment[]): Transcript {
  return {
    id: 1,
    source_id: 1,
    engine: "whisper",
    lang: "zh",
    version: 1,
    status: "translated",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
    segments,
  };
}

function hangKeHoach(p: Partial<DubPlanRow> & { i: number }): DubPlanRow {
  return {
    start: 0,
    end: 1,
    text: "",
    take: 0,
    slot: 1,
    avail: 1,
    speed: 1,
    need: 0,
    trang_thai: "vua",
    ...p,
  };
}

function chiTiet(segments: Segment[]): TranslationDetail {
  return {
    id: 4,
    transcript_id: 1,
    engine: "opus",
    lang: "vi",
    status: "done",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    segments,
    cps: { max_cps: 21, rows: [] },
  };
}

// ---------------------------------------------------------------------------

describe("doDai: san 0,01 de phep chia khong no", () => {
  it("doan binh thuong tra dung hieu", () => {
    assert.equal(doDai({ start: 1, end: 3 }), 2);
  });

  it("doan dai 0 tra SAN 0,01 — khong tra 0", () => {
    assert.equal(doDai({ start: 5, end: 5 }), 0.01);
  });

  it("doan AM (du lieu hong) cung bi kep ve san", () => {
    assert.equal(doDai({ start: 5, end: 2 }), 0.01);
  });
});

describe("soVi: dau phay thap phan, khong phu thuoc ICU", () => {
  it("doi dau cham thanh dau phay", () => {
    assert.equal(soVi(21.04, 1), "21,0");
    assert.equal(soVi(1.724, 2), "1,72");
  });

  it("so nguyen van co du chu so thap phan", () => {
    assert.equal(soVi(3, 1), "3,0");
    assert.equal(soVi(3, 2), "3,00");
  });

  it("lam tron theo toFixed, khong cat", () => {
    assert.equal(soVi(1.999, 2), "2,00");
  });
});

describe("tiLeNen: doc `need` cua may chu, KHONG tu chia", () => {
  it("co `need` duong thi tra nguyen so may chu", () => {
    const h = hangKeHoach({ i: 0, take: 3.2, slot: 2.04, avail: 4.36, need: 0.734 });
    assert.equal(tiLeNen(h), 0.734);
  });

  it("thieu `need` thi tu chia theo `avail` — KHONG chia theo `slot`", () => {
    const h = hangKeHoach({ i: 0, take: 3.2, slot: 2.04, avail: 4.36, need: 0 });
    const r = tiLeNen(h);
    assert.ok(r !== null, "phai chia duoc");
    assert.ok(Math.abs(r - 3.2 / 4.36) < 1e-9, `phai chia theo avail, do duoc ${r}`);
  });

  it("`need` va `avail` deu khong duong ⇒ null (KHONG phai 0)", () => {
    assert.equal(tiLeNen(hangKeHoach({ i: 0, take: 3.2, avail: 0, need: 0 })), null);
  });

  it("chua co take ⇒ null — 'chua long' khac 'take dai 0 giay'", () => {
    assert.equal(tiLeNen(hangKeHoach({ i: 0, take: 0, need: 0 })), null);
  });

  it("hang vang mat (null/undefined) ⇒ null", () => {
    assert.equal(tiLeNen(null), null);
    assert.equal(tiLeNen(undefined), null);
  });

  it("`need` la NaN/Infinity thi BO, khong truyen so hong ra", () => {
    assert.equal(tiLeNen(hangKeHoach({ i: 0, need: Number.NaN, take: 0 })), null);
    assert.equal(tiLeNen(hangKeHoach({ i: 0, need: Number.POSITIVE_INFINITY, take: 0 })), null);
  });
});

describe("bangCps: bang tra theo `Segment.i`", () => {
  it("dung khoa va ba truong, doi ten max_cps -> maxCps", () => {
    const cps: TranslationCps = {
      max_cps: 21,
      rows: [
        { i: 0, chars: 20, window: 1, cps: 20, max_cps: 21, over: false },
        { i: 1, chars: 30, window: 1, cps: 30, max_cps: 21, over: true },
      ],
    };
    const m = bangCps(cps);
    assert.equal(m.size, 2);
    assert.deepEqual(m.get(0), { cps: 20, over: false, maxCps: 21 });
    assert.deepEqual(m.get(1), { cps: 30, over: true, maxCps: 21 });
  });

  it("`cps` null van giu hang — null la KHONG DO DUOC, khong phai vang mat", () => {
    const m = bangCps({ max_cps: 21, rows: [{ i: 7, chars: 5, window: 0, cps: null, max_cps: 21, over: false }] });
    assert.equal(m.size, 1);
    assert.deepEqual(m.get(7), { cps: null, over: false, maxCps: 21 });
  });

  it("bang rong khi khong co CPS", () => {
    assert.equal(bangCps(null).size, 0);
    assert.equal(bangCps(undefined).size, 0);
  });
});

describe("viecCuaBanGhi: ba nguon viec, gop lai", () => {
  it("ban ghi null ⇒ khong co viec", () => {
    assert.deepEqual(viecCuaBanGhi(null, null, new Map(), new Set()), []);
  });

  it("`suspect` cua may chu thanh viec 'nghi ngo phien am'", () => {
    const t = banGhi([doan({ i: 0, suspect: true }), doan({ i: 1, suspect: false })]);
    const v = viecCuaBanGhi(t, null, new Map(), new Set());
    assert.equal(v.length, 1);
    assert.deepEqual(v[0], { i: 0, loai: "nghi-ngo", nhan: "nghi ngờ phiên âm" });
  });

  it("co `over` cua may chu thanh viec CPS, nhan co so 1 chu so thap phan", () => {
    const t = banGhi([doan({ i: 2 })]);
    const cps: TranslationCps = { max_cps: 21, rows: [{ i: 2, chars: 30, window: 1, cps: 21.04, max_cps: 21, over: true }] };
    const v = viecCuaBanGhi(t, cps, new Map(), new Set());
    assert.equal(v.length, 1);
    assert.equal(v[0].loai, "cps");
    assert.equal(v[0].nhan, "CPS 21,0");
  });

  it("`over` true ma `cps` null ⇒ nhan tron, KHONG bia so", () => {
    const t = banGhi([doan({ i: 3 })]);
    const cps: TranslationCps = { max_cps: 21, rows: [{ i: 3, chars: 5, window: 0, cps: null, max_cps: 21, over: true }] };
    const v = viecCuaBanGhi(t, cps, new Map(), new Set());
    assert.equal(v.length, 1);
    assert.equal(v[0].nhan, "CPS cao");
  });

  it("`over` false thi KHONG co viec CPS du cps cao", () => {
    const t = banGhi([doan({ i: 0 })]);
    const cps: TranslationCps = { max_cps: 21, rows: [{ i: 0, chars: 30, window: 1, cps: 30, max_cps: 21, over: false }] };
    assert.deepEqual(viecCuaBanGhi(t, cps, new Map(), new Set()), []);
  });

  it("nen > NGUONG_NEN thanh viec 'nen', nhan 2 chu so", () => {
    const t = banGhi([doan({ i: 4 })]);
    const kh = new Map<number, DubPlanRow>([[4, hangKeHoach({ i: 4, take: 1.72, avail: 1, need: 1.72 })]]);
    const v = viecCuaBanGhi(t, null, kh, new Set());
    assert.equal(v.length, 1);
    assert.equal(v[0].loai, "nen");
    assert.equal(v[0].nhan, "nén 1,72×");
  });

  it("nen DUNG BANG nguong thi chua tinh — so sanh la `>`", () => {
    const t = banGhi([doan({ i: 4 })]);
    const kh = new Map<number, DubPlanRow>([[4, hangKeHoach({ i: 4, need: NGUONG_NEN })]]);
    assert.deepEqual(viecCuaBanGhi(t, null, kh, new Set()), []);
  });

  it("da duyet thi viec cua doan do BIEN MAT", () => {
    const t = banGhi([doan({ i: 0, suspect: true }), doan({ i: 1, suspect: true })]);
    const v = viecCuaBanGhi(t, null, new Map(), new Set([0]));
    assert.equal(v.length, 1);
    assert.equal(v[0].i, 1);
  });

  it("mot doan co the mang NHIEU viec cung luc", () => {
    const t = banGhi([doan({ i: 0, suspect: true })]);
    const cps: TranslationCps = { max_cps: 21, rows: [{ i: 0, chars: 30, window: 1, cps: 30, max_cps: 21, over: true }] };
    const kh = new Map<number, DubPlanRow>([[0, hangKeHoach({ i: 0, need: 2 })]]);
    const v = viecCuaBanGhi(t, cps, kh, new Set());
    assert.deepEqual(v.map((x) => x.loai), ["nghi-ngo", "cps", "nen"]);
  });
});

describe("viecCuaDoan: loc theo i", () => {
  it("chi tra viec cua dung doan", () => {
    const ds = [
      { i: 0, loai: "cps" as const, nhan: "a" },
      { i: 1, loai: "nen" as const, nhan: "b" },
      { i: 0, loai: "nen" as const, nhan: "c" },
    ];
    assert.deepEqual(viecCuaDoan(ds, 0).map((v) => v.nhan), ["a", "c"]);
    assert.deepEqual(viecCuaDoan(ds, 9), []);
  });
});

describe("duongOng: sau buoc, bon trang thai", () => {
  function vao(p: Partial<DauVaoDuongOng>): DauVaoDuongOng {
    return {
      coBanGhi: false,
      engineAsr: null,
      asrState: null,
      coBanDich: false,
      engineMt: null,
      soViec: 0,
      dubState: null,
      ghepState: null,
      coFileXuat: false,
      ...p,
    };
  }

  /**
   * BƯỚC "PHIÊN ÂM" PHẢI NÓI ĐANG CHẠY, KHÔNG NÓI "CHƯA NẠP".
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng báo: "phần phiên âm cũng ghi là chưa nạp chứ ko
   * ghi là đang chạy"). Bản cũ chỉ có hai nhánh theo `coBanGhi`, nên suốt 20 phút bóc
   * băng một video dài thanh bước ghi "chưa nạp" và vẽ ô tròn RỖNG — y như chưa bấm gì.
   * Người dùng không phân biệt được "đang chạy" với "đã chết".
   *
   * `queued` KHÔNG được vẽ như `todo`: job đã nằm trong hàng đợi, bấm lại không được, nên
   * hiện "chưa nạp" là nói sai và mời người dùng bấm một nút không có tác dụng.
   */
  it("asr dang chay: 'dang phien am', state running — KHONG phai 'chua nap'", () => {
    const b = duongOng(vao({ asrState: "running" }));
    assert.equal(b[0].state, "running", `state phải là running, đo được ${b[0].state}`);
    assert.equal(b[0].note, "đang phiên âm…");
  });

  it("asr dang CHO: 'cho toi luot' nhung VAN la running, khong phai todo", () => {
    const b = duongOng(vao({ asrState: "queued" }));
    assert.equal(b[0].state, "running");
    assert.equal(b[0].note, "chờ tới lượt");
  });

  it("asr done ma chua kip co ban ghi: 'dang nap lai', khong noi doi la chua nap", () => {
    const b = duongOng(vao({ asrState: "done" }));
    assert.equal(b[0].state, "running");
    assert.equal(b[0].note, "đang nạp lại…");
  });

  it("asr loi: blocked va ly do doc duoc", () => {
    const b = duongOng(vao({ asrState: "failed" }));
    assert.equal(b[0].state, "blocked");
    assert.equal(b[0].note, "lỗi — xem hàng đợi");
  });

  it("asr bi ngat: blocked, va noi ro chay lai duoc", () => {
    const b = duongOng(vao({ asrState: "interrupted" }));
    assert.equal(b[0].state, "blocked");
    assert.equal(b[0].note, "bị ngắt — chạy lại được");
  });

  it("JOB DANG CHAY thi thang ban ghi cu — chay lai phai hien 'dang phien am'", () => {
    // 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng: "#109 phiên âm · fw-large-v3-turbo — 5% khi mà như
    // này ý thì state của cái header phiên âm cx phải đổi state. Nó cứ tick mãi").
    //
    // Đo trên dữ liệu thật: nguồn 6 đã có BA transcript (#23, #24, #26) từ các job `asr`
    // `done` trước, nên `coBanGhi === true`. Job **#109** (`asr`, `running`, `prog=0.05`,
    // tạo 15:41:22) đang chạy — nhưng bản trước xét `coBanGhi` TRƯỚC TIÊN nên bước vẫn vẽ
    // dấu tích và ghi engine cũ suốt 20 phút bóc băng.
    const b = duongOng(vao({ coBanGhi: true, engineAsr: "fw-large-v3", asrState: "running" }));
    assert.equal(b[0].state, "running", "job đang chạy mà bước vẫn 'done' là lỗi người dùng báo");
    assert.equal(b[0].note, "đang phiên âm…");
  });

  it("JOB CHO thi cung thang ban ghi cu — hang doi FIFO nghia la no SAP chay that", () => {
    // Bài CŨ ở đây ghim điều ngược lại, và nó SAI. Lý do cũ: "bấm Phiên âm hai lần thì job
    // thứ hai còn queued, bước đã xong không được trông như đang chạy lại".
    //
    // 🔴 DỮ LIỆU THẬT BÁC BỎ LÝ DO ĐÓ: hàng đợi chạy FIFO, nên job `queued` của lần bấm
    // trước chạy TRƯỚC job mới. Đo được trên chính máy này:
    //
    //     #88  asr  done  src=2  created=13:57:11  finished=14:00:14
    //     #89  asr  done  src=2  created=13:59:26  finished=14:03:15
    //
    // #89 tạo SAU #88 và xong SAU #88 — tức job thứ hai THẬT SỰ CHẠY, trong lúc bản ghi
    // của job thứ nhất đã tồn tại. Nếu bước nói "xong" trong khoảng 13:59–14:03 thì nó nói
    // dối đúng khoảng thời gian người dùng cần biết máy đang làm gì.
    const b = duongOng(vao({ coBanGhi: true, engineAsr: "fw-large-v3", asrState: "queued" }));
    assert.equal(b[0].state, "running", "job đang CHỜ thì bước phải nói đang chờ, không phải xong");
    assert.equal(b[0].note, "chờ tới lượt");
  });

  it("JOB LOI thi thang ban ghi cu — nguoi dung vua bam chay lai va no hong", () => {
    // Xét `failed` TRƯỚC `coBanGhi`: bản ghi cũ vẫn tồn tại, nhưng lần chạy lại vừa hỏng.
    // Hiện dấu tích của bản ghi cũ là giấu mất lỗi.
    const b = duongOng(vao({ coBanGhi: true, engineAsr: "fw-large-v3", asrState: "failed" }));
    assert.equal(b[0].state, "blocked");
    assert.equal(b[0].note, "lỗi — xem hàng đợi");
  });

  it("KHONG co job nao thi ban ghi van thang — do la bang chung ben nhat", () => {
    // Vế còn lại, phải giữ: không có job nào đang nói khác thì bản ghi là sự thật.
    const b = duongOng(vao({ coBanGhi: true, engineAsr: "fw-large-v3", asrState: null }));
    assert.equal(b[0].state, "done");
    assert.equal(b[0].note, "fw-large-v3");
  });

  it("luon tra dung sau buoc, dung thu tu", () => {
    const b = duongOng(vao({}));
    assert.deepEqual(b.map((x) => x.id), ["asr", "dich", "duyet", "long", "ghep", "xuat"]);
  });

  it("chua co ban ghi: asr 'chua nap', dich 'cho phien am'", () => {
    const b = duongOng(vao({}));
    assert.equal(b[0].state, "todo");
    assert.equal(b[0].note, "chưa nạp");
    assert.equal(b[1].state, "todo");
    assert.equal(b[1].note, "chờ phiên âm");
  });

  it("co ban ghi chua dich: buoc dich BI CHAN (khong phai todo)", () => {
    const b = duongOng(vao({ coBanGhi: true, engineAsr: "whisper" }));
    assert.equal(b[0].state, "done");
    assert.equal(b[0].note, "whisper");
    assert.equal(b[1].state, "blocked");
    assert.equal(b[1].note, "chưa dịch");
  });

  it("chua co ban dich: buoc duyet 'cho ban dich' va state todo", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: false }));
    assert.equal(b[2].state, "todo");
    assert.equal(b[2].note, "chờ bản dịch");
  });

  it("con viec: duyet bi chan voi so viec that", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 187 }));
    assert.equal(b[2].state, "blocked");
    assert.equal(b[2].note, "còn 187 việc");
  });

  it("het viec: duyet done", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0 }));
    assert.equal(b[2].state, "done");
    assert.equal(b[2].note, "hết việc");
  });

  // 🔴 LUẬT MỚI: duyệt là TUỲ CHỌN, không phải cửa chặn. Bài cũ ở đây ghim
  // `"cần duyệt xong"` — hành vi chủ dự án bác bỏ. Giữ nó là giữ một cửa chặn
  // không ai muốn, và tệ hơn: nó khiến chữ "duyệt" thành một thủ tục bấm cho có.
  it("con viec va CHUA long: buoc long VAN chay duoc, khong doi duyet", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 5, dubState: null }));
    assert.equal(b[3].state, "todo");
    assert.equal(b[3].note, "chưa chạy");
  });

  it("dub failed KHAC cancelled: failed la bi-chan, cancelled la todo", () => {
    const failed = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "failed" }));
    assert.equal(failed[3].state, "blocked");
    assert.equal(failed[3].note, "lỗi — xem hàng đợi");

    const huy = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "cancelled" }));
    assert.equal(huy[3].state, "todo");
    assert.equal(huy[3].note, "đã huỷ");
  });

  it("interrupted la bi-chan nhung chay lai duoc", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "interrupted" }));
    assert.equal(b[3].state, "blocked");
    assert.equal(b[3].note, "bị ngắt — chạy lại được");
  });

  it("queued hien la dang chay (running), khong phai todo", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "queued" }));
    assert.equal(b[3].state, "running");
    assert.equal(b[3].note, "chờ tới lượt");
  });

  it("ghep bi chan khi dub chua done", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "running" }));
    assert.equal(b[4].state, "todo");
    assert.equal(b[4].note, "cần lồng tiếng xong");
  });

  it("xuat chi done khi CO FILE", () => {
    const chua = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "done", ghepState: "done", coFileXuat: false }));
    assert.equal(chua[5].state, "todo");
    assert.equal(chua[5].note, "chưa có tệp");

    const co = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 0, dubState: "done", ghepState: "done", coFileXuat: true }));
    assert.equal(co[5].state, "done");
    assert.equal(co[5].note, "sẵn sàng");
  });

  it("xuat: 'can ghep nen' vi duyet KHONG con chan xuat", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 3, ghepState: null }));
    assert.equal(b[5].note, "cần ghép nền");
  });

  // 🔴 Ba bài dưới ghim LUẬT MỚI: duyệt là tuỳ chọn, không phải cửa chặn.
  // Bài cũ ghim `"cần duyệt xong"` ở bước lồng và ở lý do chưa xuất được — đó là
  // hành vi chủ dự án bác bỏ. Giữ chúng là giữ một cửa chặn không ai muốn.
  it("con viec CHUA duyet: long tieng VAN chay duoc (khong bi chan)", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 5, dubState: null }));
    assert.equal(b[3].state, "todo");
    assert.equal(b[3].note, "chưa chạy");
  });

  it("con viec CHUA duyet: long tieng da xong thi bao 'da long', khong doi duyet", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 5, dubState: "done" }));
    assert.equal(b[3].state, "done");
    assert.equal(b[3].note, "đã lồng");
  });

  it("chua co ban dich: long tieng noi dung ly do THAT (cho ban dich, khong phai cho duyet)", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: false, soViec: 0, dubState: null }));
    assert.equal(b[3].state, "todo");
    assert.equal(b[3].note, "chờ bản dịch");
  });

  it("con viec CHUA duyet nhung da ghep xong: xuat VAN san sang", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 9, dubState: "done", ghepState: "done", coFileXuat: true }));
    assert.equal(b[5].state, "done");
    assert.equal(b[5].note, "sẵn sàng");
  });
});

describe("lyDoChuaXuatDuoc: tra CAU, khong tra co", () => {
  it("xuat done ⇒ null (khong co ly do)", () => {
    const b = duongOng({ coBanGhi: true, engineAsr: "w", coBanDich: true, engineMt: "m", soViec: 0, dubState: "done", ghepState: "done", coFileXuat: true });
    assert.equal(lyDoChuaXuatDuoc(b), null);
  });

  it("xuat chua done ⇒ tra note cua buoc xuat", () => {
    const b = duongOng({ coBanGhi: true, engineAsr: "w", coBanDich: true, engineMt: "m", soViec: 2, dubState: null, ghepState: null, coFileXuat: false });
    assert.equal(lyDoChuaXuatDuoc(b), "cần ghép nền");
  });

  it("khong co buoc xuat trong danh sach ⇒ null", () => {
    assert.equal(lyDoChuaXuatDuoc([]), null);
  });
});

describe("tachTuKhac: danh dau tu khac giua hai ban", () => {
  it("tu giong nhau (bo dau cau, khong phan biet hoa thuong) khong bi danh dau", () => {
    const r = tachTuKhac("Hà Nội hôm nay", "hà nội, hôm nay");
    assert.deepEqual(r.filter((x) => x.khac), []);
  });

  it("tu moi bi danh dau, va giu NGUYEN VAN ca khoang trang", () => {
    const r = tachTuKhac("toi di hoc", "toi di lam");
    const khac = r.filter((x) => x.khac).map((x) => x.chu);
    assert.deepEqual(khac, ["lam"]);
    assert.equal(r.map((x) => x.chu).join(""), "toi di lam");
  });

  it("dau cau hai dau tu bi boc truoc khi so", () => {
    const r = tachTuKhac("Hà", "Hà,");
    assert.deepEqual(r.filter((x) => x.khac), []);
  });

  it("chuoi rong khong no, va tra DUNG mot manh rong (do duoc, khong doan)", () => {
    // DO DUOC: `"".split(/(\s+)/)` tra `[""]`, nen ham di qua vong `map` mot lan va tra
    // `[{chu:"",khac:false}]` — KHONG phai `[]`. Day la hanh vi that; sua ky vong chu
    // khong sua ham, vi `SegmentRow` chi noi cac manh lai va manh rong vo hai.
    assert.deepEqual(tachTuKhac("", ""), [{ chu: "", khac: false }]);
  });

  it("moi manh noi lai PHAI bang nguyen van chuoi ban dich", () => {
    const b = "  toi  di   hoc ";
    assert.equal(tachTuKhac("x", b).map((x) => x.chu).join(""), b);
  });
});

describe("raSrt: so thu tu 1..N, khong phai Segment.i", () => {
  it("danh so tu 1 va dung dinh dang HH:MM:SS,mmm", () => {
    const srt = raSrt([
      doan({ i: 5, start: 0, end: 2.5, text: "mot" }),
      doan({ i: 9, start: 2.5, end: 3, text: "hai" }),
    ]);
    assert.ok(srt.startsWith("1\n00:00:00,000 --> 00:00:02,500\nmot\n"), srt);
    assert.ok(srt.includes("2\n00:00:02,500 --> 00:00:03,000\nhai\n"), srt);
  });

  it("ban dich tay `t` duoc uu tien hon `text`", () => {
    const srt = raSrt([doan({ i: 0, start: 0, end: 1, text: "may dich", t: "nguoi sua" })]);
    assert.ok(srt.includes("nguoi sua"), srt);
    assert.ok(!srt.includes("may dich"), srt);
  });

  it("moc AM bi kep ve 0 trong dinh dang SRT", () => {
    const srt = raSrt([doan({ i: 0, start: -1, end: 1, text: "x" })]);
    assert.ok(srt.includes("00:00:00,000"), srt);
  });

  it("danh sach rong ⇒ chuoi rong", () => {
    assert.equal(raSrt([]), "");
  });
});

describe("chuCuaDoan: mot cho quyet, ba cho doc", () => {
  const banDich = new Map<number, string>([[0, "ban dich"]]);

  it("goc bien-tap doc BAN GOC", () => {
    assert.equal(chuCuaDoan(doan({ i: 0, text: "goc" }), "bien-tap", banDich), "goc");
  });

  it("goc doi-chieu va long-tieng doc BAN DICH", () => {
    assert.equal(chuCuaDoan(doan({ i: 0, text: "goc" }), "doi-chieu", banDich), "ban dich");
    assert.equal(chuCuaDoan(doan({ i: 0, text: "goc" }), "long-tieng", banDich), "ban dich");
  });

  it("khong co trong bang thi lui ve `seg.t`, roi `\"\"`", () => {
    assert.equal(chuCuaDoan(doan({ i: 1, text: "goc", t: "sua tay" }), "doi-chieu", banDich), "sua tay");
    assert.equal(chuCuaDoan(doan({ i: 1, text: "goc" }), "doi-chieu", banDich), "");
  });
});

describe("bangBanDich: `t` uu tien hon `text`", () => {
  it("dung khoa theo i va uu tien ban sua tay", () => {
    const m = bangBanDich(chiTiet([
      doan({ i: 0, text: "may" }),
      doan({ i: 1, text: "may 1", t: "nguoi 1" }),
    ]));
    assert.equal(m.get(0), "may");
    assert.equal(m.get(1), "nguoi 1");
  });

  it("chi tiet null ⇒ bang rong", () => {
    assert.equal(bangBanDich(null).size, 0);
  });
});

describe("dungDong: cau noi duy nhat giua API va giao dien", () => {
  it("ban ghi null ⇒ khong co dong", () => {
    assert.deepEqual(dungDong(null, null, null, new Map(), new Set()), []);
  });

  it("ban goc tu transcript, ban dich tu translation — HAI route khac nhau", () => {
    const t = banGhi([doan({ i: 0, start: 0, end: 2.04, text: "你绝对没吃过" })]);
    const d = chiTiet([doan({ i: 0, text: "Bạn chắc chắn chưa từng ăn" })]);
    const [row] = dungDong(t, d, null, new Map(), new Set());
    assert.equal(row.text, "你绝对没吃过");
    assert.equal(row.dich, "Bạn chắc chắn chưa từng ăn");
  });

  it("doan KHONG co trong ban dich ⇒ dich = \"\", KHONG chep ban goc vao", () => {
    const t = banGhi([doan({ i: 0, text: "goc" })]);
    const [row] = dungDong(t, chiTiet([]), null, new Map(), new Set());
    assert.equal(row.dich, "");
    assert.equal(row.text, "goc");
  });

  it("ban dich tay `t` thang `text` cua ban dich", () => {
    const t = banGhi([doan({ i: 0 })]);
    const d = chiTiet([doan({ i: 0, text: "may", t: "sua" })]);
    assert.equal(dungDong(t, d, null, new Map(), new Set())[0].dich, "sua");
  });

  it("chua co bang CPS ⇒ cps null, cpsOver false, maxCps 0", () => {
    const t = banGhi([doan({ i: 0 })]);
    const [row] = dungDong(t, null, null, new Map(), new Set());
    assert.equal(row.cps, null);
    assert.equal(row.cpsOver, false);
    assert.equal(row.maxCps, 0);
  });

  it("doc CPS/co over tu bang cua may chu", () => {
    const t = banGhi([doan({ i: 3 })]);
    const cps: TranslationCps = { max_cps: 21, rows: [{ i: 3, chars: 44, window: 2, cps: 22, max_cps: 21, over: true }] };
    const [row] = dungDong(t, null, cps, new Map(), new Set());
    assert.equal(row.cps, 22);
    assert.equal(row.cpsOver, true);
    assert.equal(row.maxCps, 21);
  });

  it("tiLeNen null khi chua long, khac 0", () => {
    const t = banGhi([doan({ i: 0 })]);
    assert.equal(dungDong(t, null, null, new Map(), new Set())[0].tiLeNen, null);
  });

  it("daDuyet doc tu tap cua App", () => {
    const t = banGhi([doan({ i: 0 }), doan({ i: 1 })]);
    const rows = dungDong(t, null, null, new Map(), new Set([1]));
    assert.equal(rows[0].daDuyet, false);
    assert.equal(rows[1].daDuyet, true);
  });

  it("giu NGUYEN start/end/suspect cua may chu", () => {
    const t = banGhi([doan({ i: 0, start: 4.36, end: 5.58, suspect: true })]);
    const [row] = dungDong(t, null, null, new Map(), new Set());
    assert.equal(row.start, 4.36);
    assert.equal(row.end, 5.58);
    assert.equal(row.suspect, true);
  });
});

describe("viecCuaDong: doc tu chinh dong", () => {
  function dong(p: Partial<ReturnType<typeof dungDong>[number]>): ReturnType<typeof dungDong>[number] {
    return {
      i: 0,
      start: 0,
      end: 1,
      text: "",
      dich: "",
      suspect: false,
      cps: null,
      cpsOver: false,
      maxCps: 0,
      tiLeNen: null,
      daDuyet: false,
      ...p,
    };
  }

  it("dong sach ⇒ khong co viec", () => {
    assert.deepEqual(viecCuaDong(dong({})), []);
  });

  it("da duyet ⇒ HET viec, du con ba co", () => {
    const d = dong({ daDuyet: true, suspect: true, cpsOver: true, tiLeNen: 3 });
    assert.deepEqual(viecCuaDong(d), []);
  });

  it("duyet chua xong thi gop du ba loai", () => {
    const d = dong({ suspect: true, cpsOver: true, cps: 21.04, tiLeNen: 1.724 });
    assert.deepEqual(viecCuaDong(d).map((v) => v.loai), ["nghi-ngo", "cps", "nen"]);
    assert.deepEqual(viecCuaDong(d).map((v) => v.nhan), ["nghi ngờ phiên âm", "CPS 21,0", "nén 1,72×"]);
  });

  it("cpsOver ma cps null ⇒ nhan tron", () => {
    assert.equal(viecCuaDong(dong({ cpsOver: true, cps: null }))[0].nhan, "CPS cao");
  });

  it("nen dung bang nguong chua tinh", () => {
    assert.deepEqual(viecCuaDong(dong({ tiLeNen: NGUONG_NEN })), []);
  });
});

describe("viecCuaDongList: gop ca danh sach", () => {
  it("noi viec cua moi dong, giu thu tu", () => {
    const ds = [
      { i: 0, suspect: true },
      { i: 1, suspect: false },
      { i: 2, suspect: true },
    ].map((p) => ({
      i: p.i, start: 0, end: 1, text: "", dich: "", suspect: p.suspect,
      cps: null, cpsOver: false, maxCps: 0, tiLeNen: null, daDuyet: false,
    }));
    assert.deepEqual(viecCuaDongList(ds).map((v) => v.i), [0, 2]);
  });

  it("danh sach rong ⇒ rong", () => {
    assert.deepEqual(viecCuaDongList([]), []);
  });
});

// ---------------------------------------------------------------------------
// PANEL "HÀNG ĐỢI" — dựng từ `jobs` THẬT, không phải chữ viết cứng.
//
// 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng gửi ảnh chụp panel và nói: *"hàng đợi ở đây có ghi
// mấy cái đang chạy đâu"*). `Studio.tsx` chứa bốn dòng JSX VIẾT CỨNG:
//
//     <QueueItem name="#37 phiên âm · faster-whisper" state="xong" />
//     <QueueItem name="#4 dịch · opus-mt" state="xong" />
//     <QueueItem name="#36 lồng tiếng · vieneu-v3" state="xong" />
//     <QueueItem name="#38 ghép nền · htdemucs" state={...} />
//     <li>ollama đang chạy · vram 2524 MiB</li>
//
// Đó là dữ liệu mẫu bê từ `_lovable-code`, không đọc `jobs` và không đọc
// `GET /api/status`. Job đang chạy vẫn hiện "xong"; `#37`/`#4`/`#36`/`#38` có thể không
// tồn tại. Panel ấy là chỗ người dùng NHÌN ĐỂ BIẾT máy đang làm gì — nó nói dối.
//
// Ba trạng thái phải phân biệt được bằng mắt: đang chạy (kèm %), đang chờ, đã xong/lỗi.
// ---------------------------------------------------------------------------

function job(p: Partial<Job> & { id: number }): Job {
  return {
    workspace: 1,
    type: "asr",
    engine: "fw-large-v3-turbo",
    phase: "asr:fw-large-v3-turbo",
    state: "queued",
    cancel_requested: false,
    attempts: 0,
    progress: 0,
    log_tail: "",
    error: null,
    payload: {},
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    ...p,
  };
}

describe("hangDoi: panel hàng đợi đọc `jobs` thật", () => {
  it("job DANG CHAY phai hien 'dang-chay', khong phai 'xong'", () => {
    const [d] = hangDoi([job({ id: 7, state: "running", progress: 0.42 })]);
    assert.equal(d.trangThai, "dang-chay");
    assert.equal(d.phanTram, 42, `phải đổi 0..1 sang %, đo được ${d.phanTram}`);
  });

  it("dang chay ma chua co tien do: KHONG ve thanh 0%", () => {
    // `progress === 0` nghĩa là "chưa tới mốc nào", không phải "0%". Vẽ thanh 0% làm
    // người dùng tưởng job đứng im.
    const [d] = hangDoi([job({ id: 7, state: "running", progress: 0 })]);
    assert.equal(d.trangThai, "dang-chay");
    assert.equal(d.phanTram, null);
  });

  it("dang CHO khac dang CHAY — deu khong phai 'xong'", () => {
    const [d] = hangDoi([job({ id: 8, state: "queued" })]);
    assert.equal(d.trangThai, "cho");
    assert.equal(d.phanTram, null);
  });

  it("job hong va job bi huy deu la 'loi' — khong duoc to mau xanh", () => {
    for (const s of ["failed", "interrupted", "cancelled"] as const) {
      const [d] = hangDoi([job({ id: 9, state: s })]);
      assert.equal(d.trangThai, "loi", `state ${s} phải là lỗi, đo được ${d.trangThai}`);
    }
  });

  it("nhan co ten loai TIENG VIET va engine that", () => {
    const [d] = hangDoi([job({ id: 11, type: "translate", engine: "deepseek-web" })]);
    assert.equal(d.nhan, "dịch · deepseek-web");
  });

  it("engine null thi nhan khong co dau ' · ' tho", () => {
    const [d] = hangDoi([job({ id: 12, type: "ingest", engine: null })]);
    assert.equal(d.nhan, "nạp");
  });

  it("MOI NHAT TRUOC, va cat dung `gioiHan`", () => {
    // Hàng đợi thật đã đo được 96 job; đổ hết vào panel 256 px thì không đọc được gì.
    const ds = [job({ id: 1 }), job({ id: 5 }), job({ id: 3 }), job({ id: 9 })];
    const ra = hangDoi(ds, 3);
    assert.deepEqual(ra.map((d) => d.id), [9, 5, 3]);
  });

  it("hang doi rong ⇒ mang rong, khong nem", () => {
    assert.deepEqual(hangDoi([]), []);
  });
});

describe("dongMayChu: chan panel doc /api/status that", () => {
  it("chua doc duoc (null) thi NOI RO, khong in so 0", () => {
    const s = dongMayChu(null);
    assert.match(s, /chưa đọc được/, `phải nói rõ chưa đọc được, nhận ${JSON.stringify(s)}`);
  });

  it("doc duoc thi in so THAT tu may chu", () => {
    const st: Status = {
      queue_depth: 3,
      running: [92],
      current_phase: "asr:fw-large-v3-turbo",
      phase_switches: 9,
      vram: 1518,
      vram_unit: "MiB",
      ollama: "up",
    };
    const s = dongMayChu(st);
    assert.match(s, /hàng đợi 3/);
    assert.match(s, /ollama up/);
    assert.match(s, /vram 1518 MiB/);
    assert.doesNotMatch(s, /2524/, "2524 là con số VIẾT CỨNG trong bản cũ, không được quay lại");
  });

  it("vram null thi bo dong vram, khong in 'vram null'", () => {
    const st: Status = {
      queue_depth: 0, running: [], current_phase: null, phase_switches: 1,
      vram: null, vram_unit: "MiB", ollama: "down",
    };
    assert.doesNotMatch(dongMayChu(st), /vram/);
  });
});
// ---------------------------------------------------------------------------

// UOC LUONG TIEN DO — do tren 34 lan chay `asr` THAT cua may nay.

//

// 🔴 VI SAO CAN: `Job.progress` KHONG phai so do tien do. Do duoc job #113 dung nguyen

// `0.05` suot thoi gian chay, va moi job `done` nhay thang `1.0`.

//

// DO DUOC hai duong chay cua CUNG `type = "asr"`, nhanh cham gap 20 lan:

//

//   "boc bang" (ASR thuan)   17 mau:  video  279 s -> 12-46 s

//                                    video 1249 s -> 41-73 s

//   "dung OCR" (OCR + ASR)   17 mau:  video  279 s -> 178-201 s

//                                    video 1249 s -> 424-448 s

//

// Hai nhom KHONG chong nhau mot giay nao, va `phase` cua ca hai GIONG NHAU

// (`asr:fw-large-v3`) — nen khong phan biet duoc bang truong co san.

// ---------------------------------------------------------------------------



const T0 = Date.parse("2026-11-01T10:00:00Z");



function daXong(giay: number, loai = "asr"): { type: string; state: string; started_at: string; finished_at: string } {

  return {

    type: loai,

    state: "done",

    started_at: new Date(T0).toISOString(),

    finished_at: new Date(T0 + giay * 1000).toISOString(),

  };

}



describe("uocLuongTienDo", () => {

  it("KHONG uoc luong khi job khong chay — tra null, khong bia so", () => {

    const j = { type: "asr", state: "done", started_at: new Date(T0).toISOString() };

    assert.equal(uocLuongTienDo(j, 279, [], T0 + 10_000), null);

  });



  it("KHONG uoc luong khi thieu started_at", () => {

    const j = { type: "asr", state: "running", started_at: null };

    assert.equal(uocLuongTienDo(j, 279, [], T0), null);

  });



  it("KHONG uoc luong translate/dub — do duoc chung dao dong qua rong", () => {

    // `translate` chay 4-57 s va `dub` 29-265 s tren cung mot do dai video, nen trung vi

    // khong co nghia. Tha khong hien gi con hon hien mot thanh chay sai nhip.

    const j = { type: "translate", state: "running", started_at: new Date(T0).toISOString() };

    assert.equal(uocLuongTienDo(j, 279, [daXong(10, "translate")], T0 + 5000), null);

  });



  it("chua co lich su thi dung mo hinh NHANH — da so nguon chay nhanh", () => {

    // DO DUOC: chon nhanh cham sai gap 10 lan o 4/6 nguon dau tien:

    //   #2 uoc 436 s thuc 41 s (+963 %), #8 uoc 185 s thuc 15 s (+1133 %)

    // Mo hinh nhanh cho video 279 s: 0,0484 * 279 + 4,5 = 18,0 s

    const j = { type: "asr", state: "running", started_at: new Date(T0).toISOString() };

    const u = uocLuongTienDo(j, 279, [], T0 + 9000);

    assert.ok(u !== null);

    assert.ok(Math.abs(u.tiLe - 0.5) < 0.05, `tiLe phai ~0,5, do duoc ${u.tiLe}`);

    assert.ok(u.conLaiGiay > 8 && u.conLaiGiay < 10, `conLai phai ~9 s, do duoc ${u.conLaiGiay}`);

  });



  it("co lich su thi BAM lich su, khong bam mo hinh", () => {

    // Nguon 6: 5/5 lan chay deu ~185 s. Lich su phai LAN AT mo hinh nhanh (18 s).

    // ⚠️ CON SO KY VONG, tinh tay de bai test khong phai doan:
    //     trungVi([183, 185, 186]) = 185
    //     tron w=1 voi mo hinh nhanh 18,0  ->  (185*3 + 18) / 4 = 141,75
    //     sau 92,5 s  ->  92,5 / 141,75 = 0,6527
    //
    // 🔴 Ban dau toi viet ky vong ~0,5 va bai test DO (do duoc 0,6457) — vi toi quen buoc
    // tron. Neu tron khong co tac dung thi tiLe se la 92,5/185 = 0,5; con so 0,6457 chinh
    // la bang chung buoc tron DANG chay dung.
    const ls = [daXong(183), daXong(185), daXong(186)];

    const j = { type: "asr", state: "running", started_at: new Date(T0).toISOString() };

    const u = uocLuongTienDo(j, 279, ls, T0 + 92_500);

    assert.ok(u !== null);

    assert.ok(
      Math.abs(u.tiLe - 0.6527) < 0.02,
      `tiLe phai ~0,653 (tron lich su 185 s voi mo hinh 18 s), do duoc ${u.tiLe}`,
    );

    // Phai KHAC han 0,5: neu bang 0,5 thi lich su dang duoc dung NGUYEN, tuc buoc tron da
    // bi bo mat trong luc sua.
    assert.ok(u.tiLe > 0.55, `phai thay dau vet cua buoc tron, do duoc ${u.tiLe}`);

  });



  it("da chay VUOT uoc luong ban dau thi chuyen sang mo hinh CHAM", () => {

    // DO DUOC vi sao can: nguon 2 chuyen tu ASR thuan sang OCR, nen #69..#80 bi uoc

    // 17-21 s trong khi thuc te 178-191 s — sai -89 %. Dieu kien cu

    // (`daChay > tuLichSu * 1,5`) KHONG BAO GIO dung vi 20 * 1,5 = 30 s, va o 30 s

    // thanh da cham tran 97 % nen khong con gi de chuyen.

    const ls = [daXong(18), daXong(20)];

    const j = { type: "asr", state: "running", started_at: new Date(T0).toISOString() };

    // Mo hinh cham cho 279 s: 0,2586 * 279 + 113 = 185,1 s. Sau 100 s: tiLe ~0,54.

    const u = uocLuongTienDo(j, 279, ls, T0 + 100_000);

    assert.ok(u !== null);

    assert.ok(u.tiLe > 0.4 && u.tiLe < 0.7, `phai theo mo hinh cham (~0,54), do duoc ${u.tiLe}`);

  });



  it("tiLe KHONG BAO GIO cham 1 khi job con chay", () => {

    // Cham 1 la noi doi "xong roi". Tran 0,97 giu cho thanh con khoang trong.

    const j = { type: "asr", state: "running", started_at: new Date(T0).toISOString() };

    const u = uocLuongTienDo(j, 279, [daXong(18)], T0 + 10_000_000);

    assert.ok(u !== null);

    assert.equal(u.tiLe, 0.97);

    assert.equal(u.conLaiGiay, 0);

  });

});



describe("trungViThoiGianChay", () => {

  it("LOAI NGOAI LAI — #5 chay 3701 s cho video 1249 s, gap 64 lan trung vi", () => {

    // DO DUOC: voi n = 2 thi trung vi CHINH LA trung binh hai so, nen #5 + mot mau 42 s

    // cho ra 1871 s. Mo phong tren lich su that: #27 bi uoc 1871 s trong khi thuc 42 s

    // — sai +4354 %.

    const ls = [daXong(41), daXong(3701), daXong(42), daXong(73)];

    const tv = trungViThoiGianChay(ls, "asr");

    assert.ok(tv !== null);

    assert.ok(tv < 200, `phai loai 3701 s, do duoc trung vi ${tv}`);

  });



  it("tra null khi khong co mau nao", () => {

    assert.equal(trungViThoiGianChay([], "asr"), null);

  });



  it("bo qua job chua xong", () => {

    const ls = [

      { type: "asr", state: "failed", started_at: new Date(T0).toISOString(), finished_at: new Date(T0 + 999_000).toISOString() },

      daXong(20),

    ];

    assert.equal(trungViThoiGianChay(ls, "asr"), 20);

  });

});



describe("chuConLai", () => {

  it("LUON co chu ~ — day la uoc luong, khong phai so do", () => {

    // Ghi "con 2 phut" khong co "~" la bien mot phong doan thanh loi hua.

    assert.equal(chuConLai(130), "~2 phút 10 giây còn lại");

    assert.equal(chuConLai(45), "~45 giây còn lại");

    assert.equal(chuConLai(120), "~2 phút còn lại");

    assert.equal(chuConLai(2), "~sắp xong");

  });

  it("0 giay van noi 'sap xong', khong noi 'con 0 giay'", () => {

    assert.equal(chuConLai(0), "~sắp xong");

  });

});


// ---------------------------------------------------------------------------
// LOP NGUON CHU — nhan, mo ta, va MAU
// ---------------------------------------------------------------------------

describe("lopCua: doc lop tu du lieu may chu", () => {
  it("nhan dung hai gia tri backend sinh ra", () => {
    assert.equal(lopCua({ layer: "mot_nguon" }), "mot_nguon");
    assert.equal(lopCua({ layer: "hai_nguon" }), "hai_nguon");
  });

  it("du lieu CU (khong co truong) tra null, KHONG doan bua mot lop", () => {
    assert.equal(lopCua({}), null);
    assert.equal(lopCua({ layer: undefined }), null);
  });

  it("gia tri la (backend doi ten) tra null thay vi nem", () => {
    assert.equal(lopCua({ layer: "ba_nguon" }), null);
    assert.equal(lopCua({ layer: "" }), null);
  });
});

describe("mauLop: VIEN va NEN theo NGUON CHU (OCR xanh la, ASR xanh bien)", () => {
  it("OCR (suspect=false) dung xanh LA", () => {
    assert.equal(mauLop({ suspect: false }).vien, "border-ocr");
    assert.equal(mauLop({ suspect: false }).nen, "bg-ocr/15");
  });

  it("ASR (suspect=true) dung xanh BIEN", () => {
    assert.equal(mauLop({ suspect: true }).vien, "border-asr");
    assert.equal(mauLop({ suspect: true }).nen, "bg-asr/15");
  });

  it("hai nguon KHONG duoc trung mau — day la ca muc dich cua no", () => {
    assert.notEqual(mauLop({ suspect: false }).vien, mauLop({ suspect: true }).vien);
    assert.notEqual(mauLop({ suspect: false }).nen, mauLop({ suspect: true }).nen);
  });

  it("khong biet (suspect undefined) dung mau trung tinh, khong to mau bia", () => {
    assert.equal(mauLop({}).vien, "border-rule");
    assert.equal(mauLop({}).nen, "");
  });

  it("layer KHONG quyet dinh mau — mot_nguon co the la ASR", () => {
    // Do duoc tren #41: 62/75 dong `mot_nguon` la do ASR ma ra. Neu to mau theo
    // `layer` thi ca loat dong do bi to xanh la — sai han y nguoi dung.
    assert.equal(mauLop({ suspect: true }).vien, "border-asr");
  });
});

describe("NHAN_LOP va moTaLop: noi RO nguon nao", () => {
  it("nhan ngan cho chip", () => {
    assert.equal(NHAN_LOP.mot_nguon, "1 nguon");
    assert.equal(NHAN_LOP.hai_nguon, "2 nguon");
  });

  it("mot_nguon + suspect=true la CHI ASR — day la thong tin nguoi doc can", () => {
    assert.equal(moTaLop({ layer: "mot_nguon", suspect: true, chuaTrong: null }),
      "chỉ ASR nghe ra");
  });

  it("mot_nguon + suspect=false la CHI OCR", () => {
    assert.equal(moTaLop({ layer: "mot_nguon", suspect: false, chuaTrong: null }),
      "chỉ OCR đọc ra");
  });

  it("doan nam trong doan khac thi noi ro so hieu doan bao", () => {
    assert.equal(moTaLop({ layer: "mot_nguon", suspect: false, chuaTrong: 7 }),
      "chỉ OCR đọc ra · nằm trong đoạn #7");
  });

  it("hai_nguon noi ca hai nguon cung doc ra", () => {
    assert.equal(moTaLop({ layer: "hai_nguon", suspect: false, chuaTrong: null }),
      "OCR và ASR cùng đọc ra câu này");
  });

  it("layer null thi noi la chua ro, khong gan bua", () => {
    assert.equal(moTaLop({ layer: null, suspect: false, chuaTrong: null }),
      "chưa rõ nguồn (bản ghi cũ)");
  });
});
