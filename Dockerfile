FROM python:3.9-slim

WORKDIR /bot

RUN apt update && apt install -y git

RUN pip install cryptography

COPY pyproject.toml poetry.lock ./
RUN pip install -U poetry
RUN poetry config virtualenvs.create false

RUN poetry export -f requirements.txt -o requirements.txt --without-hashes
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "main.py"]