/**
 * Backend GIA cho phep do **A1b** cua Task 12: giu **MOT response DAI (SSE) dang mo**.
 *
 * ## Vi sao phai la mot TIEN TRINH RIENG
 *
 * Cua so cua EVIDENCE §7 (loi `:97` cua `dev-server.mjs`) la `res.headersSent === true` tren
 * `ServerResponse` CUA PROXY luc upstream bao loi. Do duoc (review doc lap, `A2`): tren Node 24,
 * mot response **NGAN** bi cat (RST sau header, chunked dut giua, 101 roi chet, client huy giua
 * body, ke ca `res.socket.destroy()` phia server) **KHONG** lam `ClientRequest` cua proxy phat
 * `'error'` ⇒ khong vao duoc cua so do. Cai lam no phat `'error'` la **tien trinh upstream CHET
 * trong khi response con dang mo**.
 *
 * ⇒ Phep do phai (1) giu mot response DAI that su, va (2) **GIET TIEN TRINH** backend. Ca hai deu
 * doi mot tien trinh RIENG — mot server trong cung tien trinh test thi `kill()` khong co gi de giet.
 *
 * Dung: `PHUDE_T12_SSE_PORT=<cong>` (mac dinh 0 = he dieu hanh cap). In ra `PORT=<n>` tren stdout
 * de tien trinh cha doc duoc cong THAT (khong doan).
 */
import { createServer } from "node:http";

const PORT = Number(process.env.PHUDE_T12_SSE_PORT ?? 0);

const server = createServer((req, res) => {
  if ((req.url ?? "").startsWith("/api/sse")) {
    // HEADER GUI NGAY, roi giu ket noi mo va day cac nhip — day la "response DAI" cua §7.
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    res.write(": mo\n\n");
    const nhip = setInterval(() => {
      try {
        res.write(": nhip\n\n");
      } catch {
        clearInterval(nhip);
      }
    }, 100);
    res.on("close", () => clearInterval(nhip));
    return;
  }
  res.writeHead(200, { "content-type": "application/json" }).end('{"ok":true}');
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`PORT=${server.address().port}`);
});
