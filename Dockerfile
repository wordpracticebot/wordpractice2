FROM python:3.9-alpine

WORKDIR /bot

RUN apk update && apk add --update build-base bash linux-headers build-base python3-dev py-pip libwebp-dev jpeg-dev zlib-dev libffi-dev rust gcc musl-dev openssl-dev git cargo g++ freetype-dev

RUN pip install cryptography

RUN pip install -U poetry

COPY pyproject.toml poetry.lock ./

RUN poetry export -f requirements.txt -o requirements.txt --without-hashes
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]