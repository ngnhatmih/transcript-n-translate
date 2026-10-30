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
  Segment,
  Transcript,
  TranslationCps,
  TranslationDetail,
} from "../api/types.ts";
import {
  bangBanDich,
  bangCps,
  chuCuaDoan,
  doDai,
  dungDong,
  duongOng,
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
      coBanDich: false,
      engineMt: null,
      soViec: 0,
      dubState: null,
      ghepState: null,
      coFileXuat: false,
      ...p,
    };
  }

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

  it("con viec va CHUA long: buoc long 'can duyet xong'", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 5, dubState: null }));
    assert.equal(b[3].state, "todo");
    assert.equal(b[3].note, "cần duyệt xong");
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

  it("xuat: 'can duyet xong' uu tien hon 'can ghep nen'", () => {
    const b = duongOng(vao({ coBanGhi: true, coBanDich: true, soViec: 3, ghepState: null }));
    assert.equal(b[5].note, "cần duyệt xong");
  });
});

describe("lyDoChuaXuatDuoc: tra CAU, khong tra co", () => {
  it("xuat done ⇒ null (khong co ly do)", () => {
    const b = duongOng({ coBanGhi: true, engineAsr: "w", coBanDich: true, engineMt: "m", soViec: 0, dubState: "done", ghepState: "done", coFileXuat: true });
    assert.equal(lyDoChuaXuatDuoc(b), null);
  });

  it("xuat chua done ⇒ tra note cua buoc xuat", () => {
    const b = duongOng({ coBanGhi: true, engineAsr: "w", coBanDich: true, engineMt: "m", soViec: 2, dubState: null, ghepState: null, coFileXuat: false });
    assert.equal(lyDoChuaXuatDuoc(b), "cần duyệt xong");
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
