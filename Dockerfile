FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/raptor-matplotlib \
    PORT=7860

WORKDIR /app

COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN useradd --create-home --uid 10001 raptor

COPY --chown=raptor:raptor . .

# Streamlit's initial HTML uses the generic title "Streamlit" and a generic
# no-JavaScript message. Search crawlers can index that shell before the app
# updates the page in the browser, so install RAPTor's crawler-facing metadata
# directly into the static document served by Streamlit.
RUN python scripts/patch_streamlit_index.py

USER raptor

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/_stcore/health', timeout=4)"

CMD ["sh", "-c", "exec streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT} --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false"]
