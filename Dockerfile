FROM python:3.9.7

WORKDIR /app

RUN pip install poetry
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev

COPY . .
CMD ["python", "main.py"]