/** Lay MOT khoi `proxied.on("error", …)` theo DO SAU NGOAC (khong phai theo mau ket thuc). */
export function layKhoiHandler(text, tuKhoa) {
  const dau = text.indexOf(tuKhoa);
  if (dau < 0) throw new Error(`khong thay ${JSON.stringify(tuKhoa)}`);
  let i = text.indexOf("{", dau + tuKhoa.length - 1);
  if (i < 0) throw new Error("khong thay ngoac mo cua handler");
  let sau = 0;
  for (; i < text.length; i += 1) {
    if (text[i] === "{") sau += 1;
    else if (text[i] === "}") {
      sau -= 1;
      if (sau === 0) {
        const cuoi = text[i + 1] === ")" ? i + 2 : i + 1;
        return { khoi: text.slice(dau, cuoi), batDau: dau, ketThuc: cuoi };
      }
    }
  }
  throw new Error("khong dong duoc khoi handler");
}
