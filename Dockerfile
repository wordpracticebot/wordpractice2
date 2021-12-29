FROM python:3.9.7

WORKDIR /app

RUN pip install -U poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

COPY . .
CMD ["python", "main.py"]