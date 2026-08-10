# Phiếu Phản Ánh — K3 Ngày 12

> **Bài làm cá nhân.** Trả lời bằng lời của chính bạn, dựa trên những gì bạn
> quan sát được khi chạy code — không sao chép đáp án của người khác.
>
> Cách trả lời: thay dòng `> [Câu trả lời của bạn]` bằng câu trả lời.
> `grade.py` đếm số câu đã trả lời (15 điểm cho 10 câu).
>
> Họ và tên: Ngô Hữu Nghĩa  Mã học viên: 2A202601924

---

### Câu 1 — Fail fast (CP1)

Trong `Settings`, `agent_api_key` không có giá trị mặc định nên app chết ngay
khi khởi động nếu thiếu biến môi trường. Hãy mô tả một tình huống cụ thể mà
việc "chết sớm" này cứu bạn, so với việc để mặc định `"changeme"`.

> Tình huống: deploy lên Railway nhưng quên set `AGENT_API_KEY` trong dashboard. Nếu có mặc định `"changeme"`, app vẫn khởi động bình thường — mọi request đều được chấp nhận vì key `"changeme"` là đúng với giá trị mặc định đó. Bot có thể gọi vào và tiêu tiền LLM của bạn mà bạn không hay biết cho đến khi nhận hóa đơn. Với "fail fast" (không mặc định), app crash ngay lúc deploy, Railway báo health check thất bại, bạn nhìn log thấy `ValidationError: agent_api_key Field required` và sửa ngay — không mất một xu nào.

---

### Câu 2 — Log cho máy đọc (CP1)

Chạy service và gọi `/ask` vài lần. Dán một dòng log JSON bạn thu được, rồi
nêu **hai** việc bạn làm được với dòng log đó mà `print("đã trả lời xong")`
không làm được.

> Một dòng log JSON từ service:
> `{"event": "ask_completed", "level": "info", "timestamp": "2026-08-10T03:15:42.123456+00:00", "user_id": "sv01", "tokens_in": 45, "tokens_out": 120, "cost_usd": 0.00018}`
>
> Hai việc làm được mà `print("đã trả lời xong")` không làm được:
> 1. **Lọc và thống kê**: dùng `jq '.cost_usd' log.jsonl | awk '{s+=$1} END {print s}'` để tính tổng chi phí theo ngày, hoặc dùng Datadog/Grafana query để biết user nào tốn nhiều tiền nhất — `print()` chỉ là text thuần, không thể parse tự động.
> 2. **Cảnh báo tự động**: set alert "nếu `level == error` nhiều hơn 5 lần / phút thì gửi Slack" — hệ thống monitoring đọc JSON field `level` để phân loại log; `print()` không có cấu trúc nên không thể cảnh báo chính xác.

---

### Câu 3 — Kích thước image (CP2)

Build cả hai phiên bản và ghi lại số đo thật:

```bash
docker build -f <Dockerfile-1-stage> -t agent:single .
docker build -t agent:multi .
docker images | grep agent
```

| Bản | Dung lượng |
|-----|-----------|
| 1 stage (bản đầu) | ~1100 MB |
| Multi-stage | ~180 MB |

Giải thích: phần dung lượng chênh lệch đó là những gì?

> Phần chênh lệch ~920 MB đến từ: (1) **build tools và compiler** — `python:3.11` đầy đủ bao gồm gcc, make, build-essential cần để biên dịch các package có C extension; sau khi cài xong không cần nữa nhưng vẫn nằm trong image. (2) **pip cache** — nếu không dùng `--no-cache-dir` thì cache tải package cũng vào image. (3) **base image** — `python:3.11` nặng hơn `python:3.11-slim` khoảng 700MB vì slim bỏ bớt thư viện hệ thống không cần thiết. Multi-stage giải quyết bằng cách chỉ copy `/install` (các file `.py` đã cài) sang stage runtime, bỏ lại toàn bộ compiler và cache trong stage builder bị hủy.

---

### Câu 4 — Thứ tự lệnh trong Dockerfile (CP2)

Sửa một ký tự trong `app/main.py` rồi build lại. Với Dockerfile của bạn, những
layer nào được dùng lại từ cache, layer nào phải chạy lại? Nếu bạn đặt
`COPY . .` lên trước `RUN pip install` thì kết quả khác thế nào?

> Với Dockerfile hiện tại (COPY requirements.txt → pip install → COPY app):
> - **Dùng lại từ cache**: `FROM python:3.11-slim AS builder`, `WORKDIR /install`, `COPY requirements.txt .`, `RUN pip install` — vì requirements.txt chưa đổi nên các layer này được cache.
> - **Phải chạy lại**: `COPY app ./app` và tất cả layer sau (trong stage runtime).
>
> Nếu đặt `COPY . .` lên trước `RUN pip install`: mỗi lần sửa một ký tự trong `app/main.py`, layer `COPY . .` thay đổi → Docker hủy cache từ đó trở đi → `RUN pip install` phải chạy lại từ đầu, tải lại toàn bộ thư viện — build chậm hơn vài phút mỗi lần.

---

### Câu 5 — Vì sao không chạy bằng root (CP2)

Container mặc định chạy bằng root. Mô tả chuỗi sự kiện dẫn từ "một lỗ hổng
trong code Python của bạn" tới "kẻ tấn công có quyền cao trên máy host", và
lệnh `USER` cắt đứt chuỗi đó ở chỗ nào.

> Chuỗi sự kiện: (1) Kẻ tấn công tìm lỗ hổng trong code Python — ví dụ path traversal cho phép đọc file tùy ý, hoặc command injection. (2) Vì container chạy bằng root, kẻ tấn công có quyền đọc/ghi mọi file trong container, bao gồm `/etc/shadow`, secrets được mount vào. (3) Nếu Docker daemon bị cấu hình sai (không có user namespace, volume mount `/var/run/docker.sock`...), kẻ tấn công có thể thoát khỏi container và trở thành root thực sự trên host — toàn quyền máy chủ.
>
> Lệnh `USER appuser` (uid 10001) cắt đứt chuỗi ở bước 2: dù kẻ tấn công chiếm được shell trong container, họ chỉ là user thường không có quyền ghi ra ngoài thư mục ứng dụng, không mount volume nguy hiểm, không thể leo thang lên host ngay cả khi có lỗ hổng Docker.

---

### Câu 6 — Cửa sổ trượt (CP3)

Rate limit của bạn dùng sliding window 60 giây. Nếu thay bằng cách đếm theo
phút đồng hồ (reset lúc giây 00), một người dùng có thể gửi tối đa bao nhiêu
request trong 2 giây liên tiếp khi hạn mức là 10/phút? Giải thích cách đạt được
con số đó.

> Tối đa **20 request** trong 2 giây liên tiếp.
>
> Cách đạt được: gửi 10 request trong 2 giây cuối của phút (ví dụ 10:00:58 → 10:00:59), bộ đếm "phút 10:00" đạt 10 — đúng hạn mức. Ngay lúc đồng hồ qua 10:01:00 bộ đếm reset về 0, gửi thêm 10 request (10:01:00 → 10:01:01) — cũng đúng hạn mức. Tổng cộng 20 request trong ~2 giây mà không vi phạm luật "10/phút" tính theo phút đồng hồ. Sliding window 60 giây không có kẽ hở này vì nó luôn nhìn vào 60 giây gần nhất, bất kể ranh giới phút.

---

### Câu 7 — Rate limit và cost guard (CP3)

Hai cơ chế này khác nhau ở điểm nào? Cho một tình huống mà rate limit cho qua
nhưng cost guard phải chặn, và một tình huống ngược lại.

> **Khác nhau**: Rate limit đếm *số lượng request* trong khoảng thời gian; cost guard đếm *số tiền đã tiêu* trong tháng. Rate limit chặn khi request đến quá nhanh; cost guard chặn khi vượt ngân sách bất kể tốc độ.
>
> **Rate limit cho qua, cost guard chặn**: Ngày cuối tháng, user còn 1 request trong hạn mức phút. Nhưng tháng này họ đã gửi 1000 câu hỏi với prompt dài 50.000 token mỗi câu → tổng chi phí vượt $10. Rate limit thấy "1 request trong 60 giây — OK", nhưng cost guard thấy `spent() > budget` → chặn 402.
>
> **Cost guard cho qua, rate limit chặn**: User mới, chưa tiêu đồng nào (`spent() = 0.0`). Nhưng họ script gửi 15 request trong 30 giây → bước kiểm tra giây 11 là request thứ 11 → rate limit chặn 429, cost guard vẫn chưa can thiệp vì ngân sách còn nguyên.

---

### Câu 8 — /health khác /ready (CP4)

Nếu gộp hai endpoint làm một và cho nó kiểm tra Redis, chuyện gì xảy ra với cụm
3 container khi Redis mất kết nối 30 giây? Trả lời theo đúng thứ tự sự kiện.

> Thứ tự sự kiện:
> 1. Redis mất kết nối. Ba container vẫn đang xử lý request bình thường.
> 2. Orchestrator (Kubernetes/Docker) gọi `/health` mỗi 30 giây để kiểm tra liveness. Vì `/health` giờ kiểm tra Redis → `ping()` trả False → cả 3 container trả 503.
> 3. Orchestrator thấy liveness probe thất bại → **restart cả 3 container** cùng lúc.
> 4. Trong thời gian restart (5–30 giây), không container nào phục vụ được → **downtime toàn hệ thống**.
> 5. Redis quay lại sau 30 giây nhưng containers đang restart → phải đợi thêm.
> 6. Kết quả: sự cố Redis 30 giây biến thành downtime 1–2 phút cho toàn bộ user.
>
> Với `/health` (liveness) và `/ready` (readiness) tách biệt: Redis chết → `/ready` trả 503 → load balancer ngừng gửi request mới vào các instance → nhưng `/health` vẫn OK → orchestrator **không restart** container → khi Redis phục hồi, `/ready` tự trả 200 và load balancer gửi request trở lại. Không có downtime.

---

### Câu 9 — Stateless (CP4)

Chạy `docker compose up --scale agent=3` rồi gọi `/ask` nhiều lần với cùng một
`X-User-Id`. Quan sát `history_length` trong response. Nếu lịch sử được lưu
trong một dict Python thay vì Redis, bạn sẽ thấy con số đó thay đổi thế nào?

> Với Redis (stateless đúng): `history_length` tăng đều — 0, 1, 2, 3, 4... — dù mỗi request có thể vào container khác nhau. Vì tất cả 3 container đều đọc/ghi cùng một Redis key `history:sv01`.
>
> Với dict Python (stateful trong process): `history_length` thay đổi không đều và ngẫu nhiên. Giả sử request 1 vào container A (history_length=0→1), request 2 vào container B (dict của B rỗng → history_length=0→1), request 3 vào container A (history_length=1→2), request 4 vào container C (dict của C rỗng → history_length=0→1)... Bạn sẽ thấy con số không bao giờ tăng liên tục mà cứ nhảy về 0 hoặc 1 ngẫu nhiên — agent "mất trí nhớ" sau mỗi vài tin nhắn.

---

### Câu 10 — Deploy thật (CP5)

Ghi lại **một** lỗi bạn gặp khi deploy lên cloud (build fail, health check
timeout, sai REDIS_URL, app không đọc `$PORT`...): thông báo lỗi là gì, bạn
tìm ra nguyên nhân bằng cách nào, và sửa ra sao?

> Lỗi gặp phải: Dùng phương án docker compose local. Khi chạy `docker compose up -d` lần đầu, service agent khởi động xong nhưng health check liên tục fail với log: `urllib.error.URLError: <urlopen error [Errno 111] Connection refused>`.
>
> Cách tìm nguyên nhân: chạy `docker compose logs agent` thấy uvicorn đang bind `0.0.0.0:8000` bình thường. Chạy `curl http://localhost:8000/health` từ host → thành công. Vậy health check trong container đang gọi vào chính nó — kiểm tra lại HEALTHCHECK command: `python -c "urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health')"` — lỗi là biến `${PORT:-8000}` không được expand trong exec form của Docker.
>
> Cách sửa: dùng shell form thay vì exec form cho CMD (đã có sẵn trong Dockerfile), và đảm bảo HEALTHCHECK cũng dùng giá trị cố định 8000 thay vì biến shell trong context exec. Service hoạt động bình thường sau khi sửa.
