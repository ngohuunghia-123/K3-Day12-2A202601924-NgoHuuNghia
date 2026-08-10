# ── Stage 1: builder — cài dependency (có thể cần compiler) ──────────────────
FROM python:3.11-slim AS builder

WORKDIR /install

# Copy requirements trước để tận dụng Docker cache layer
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime — chỉ copy kết quả, không mang theo compiler ────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy thư viện đã cài từ builder
COPY --from=builder /install /usr/local

# Copy source code SAU (thay đổi code không cài lại thư viện)
COPY app ./app
COPY utils ./utils

# Tạo user thường — container chạy root: một lỗ hổng nhỏ = root trên host
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Kiểm tra process còn sống không (không phụ thuộc Redis)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health').read()" || exit 1

EXPOSE 8000

# Đọc PORT từ env: Railway/Render/Cloud Run tự gán cổng, không cố định 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
