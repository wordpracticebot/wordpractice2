# wordPractice

Practice your typing skills while having fun, compete with typists from around the world.

## Installation

Use [poetry](https://python-poetry.org/) to install the required dependencies.

```bash
poetry install
```

## Configuration

Create a `.env` file in the root directory of the repository.

Copy the content from `.env.example` into it and fill it with the necessary information.

```
BOT_TOKEN= # Your bot token
DATABASE_URI= # Mongodb database uri
DATABASE_NAME= # Cluster name
DBL_TOKEN= # dbl token

COMMAND_LOG= # command log webhook url
TEST_LOG= # test log webhook url
IMPORTANT_LOG= # important log webhook url
```

## Formatting

[Black](https://github.com/psf/black) is used for formatting.

## Running

[Python 3.9.7](https://www.python.org/downloads/release/python-397/) is recommended.

```
python main.py
```
