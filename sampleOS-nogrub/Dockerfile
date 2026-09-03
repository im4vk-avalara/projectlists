FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        make \
        gcc-i686-linux-gnu \
        binutils-i686-linux-gnu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# ---------------------------------------------------------------------------
# Optional: run a local LLM for the AI bridge via Ollama in Docker (an
# alternative to the default HuggingFace `transformers` backend). The bridge's
# `ollama` backend was removed, but this is the setup to re-add it:
#
#   docker run -d --name aios-ollama -p 11434:11434 \
#       -v aios-ollama:/root/.ollama ollama/ollama
#   docker exec aios-ollama ollama pull qwen2.5:3b
#   python3 host/ai-bridge/bridge.py --backend ollama --model qwen2.5:3b
#
# Behind a corporate TLS-intercepting proxy, `ollama pull` fails with
# "x509: certificate signed by unknown authority"; give the container the
# Mac's trusted CAs (Ollama is Go, honors SSL_CERT_FILE):
#
#   security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >  /tmp/aios-cas.pem
#   security find-certificate -a -p /Library/Keychains/System.keychain                          >> /tmp/aios-cas.pem
#   docker run -d --name aios-ollama -p 11434:11434 \
#       -v aios-ollama:/root/.ollama \
#       -v /tmp/aios-cas.pem:/etc/ssl/aios-cas.pem:ro -e SSL_CERT_FILE=/etc/ssl/aios-cas.pem \
#       ollama/ollama
#
# NOTE: Ollama-in-Docker on macOS is CPU-only (no GPU passthrough); the
# `transformers` backend uses the Apple GPU (MPS) and is faster for warm calls.
# ---------------------------------------------------------------------------
