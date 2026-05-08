# Clairvoyant-Optics Docker image
# Huom: Apple Silicon (M1) vain macOS-isännällä — ei toimi x86_64 Dockerilla

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Clairvoyant-Optics"
LABEL org.opencontainers.image.description="Paikallinen kasvojentunnistus valvontakameroille"

# Avoid buffering in logs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ src/
COPY models/ models/

# Create data directory for database
RUN mkdir -p /app/data /app/debug

# Run as non-root user
RUN useradd --create-home --shell /bin/bash clairvoyant
RUN chown -R clairvoyant:clairvoyant /app
USER clairvoyant

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD pgrep -f "python.*src/main.py" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
