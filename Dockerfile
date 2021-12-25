FROM python:3.9.7

WORKDIR /app

ENV PIP_NO_CACHE_DIR=false \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev

COPY . .
CMD ["python", "main.py"]