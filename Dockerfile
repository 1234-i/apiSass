FROM python:3.12-slim
ARG KUBECTL_VERSION=v1.30.8
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates bash && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH:-amd64}" in amd64|arm64) kubectl_arch="${TARGETARCH:-amd64}" ;; *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; esac \
    && curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${kubectl_arch}/kubectl" \
    && chmod +x /usr/local/bin/kubectl
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app /app/app
COPY scripts /app/scripts
COPY tests /app/tests
COPY pytest.ini /app/pytest.ini
COPY docs /app/docs
COPY .gitignore /app/.gitignore
COPY .env.example .env.real-canary.example .env.real.example /app/
RUN chmod +x /app/scripts/*.sh
EXPOSE 8080
CMD ["/app/scripts/start.sh"]
