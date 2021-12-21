# wordPractice

Practice your typing skills while having fun, compete with typists from around the world.

# How to run

### 1. Clone the repository

> `git clone https://github.com/wordPractice-Bot/wordpractice2`

### 2. Configuration

> Create a `.env` file in the root directory of the repository.
>
> Copy the content from `.env.example` into it and fill it with the necessary information.
>
> ```
> BOT_TOKEN= # Your bot token
> DATABASE_URI= # Mongodb database uri
> DATABASE_NAME= # Cluster name
> DBL_TOKEN= # dbl token
>
> COMMAND_LOG= # command log webhook url
> TEST_LOG= # test log webhook url
> IMPORTANT_LOG= # important log webhook url
> ```

### 3. Running

> ### Docker
>
> `docker compose up`
>
> ### Without Docker
>
> [Python 3.9.7](https://www.python.org/downloads/release/> python-397/) is recommended.
>
> 1. Install [Poetry](https://python-poetry.org/) using `pip > install poetry`
> 2. Install the necessary dependencies using `poetry install`
> 3. Active the poetry environment using `.venv/bin/activate`
> 4. Type `python main.py` to run

## Formatting

[Black](https://github.com/psf/black) is used for formatting.

## Contributing
