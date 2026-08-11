# The API image. Serving only — no loaders, no bake, no tippecanoe.
#
# `pip install .[api]` deliberately skips the `data` extra: geopandas, shapely and pyproj
# are loader-only and are most of the install size. The serving libraries themselves are
# base dependencies now, so the `[api]` extra adds only uvicorn — the server this image
# runs and a serverless function does not.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependency layer first, so application edits do not reinstall numpy and scipy.
COPY pyproject.toml README.md ./
COPY engine/ engine/
COPY data/ data/
COPY api/ api/
COPY bake/ bake/
COPY tiles/ tiles/

RUN pip install ".[api]"

# Render, Railway and Fly all inject $PORT. The default keeps `docker run` usable.
ENV PORT=8000
EXPOSE 8000

# One worker: each holds its own connection and the container is small. Scale out with
# instances rather than up with workers.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
