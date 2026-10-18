# Foresight backend — CPU container (Hugging Face Space, Render, Railway, Fly, ...)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FORESIGHT_DEVICE=cpu HF_HOME=/home/user/.cache/huggingface
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt
COPY --chown=user . .
USER user
# Model files are downloaded at startup from FORESIGHT_MODEL_REPO (see main.fetch_models)
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
