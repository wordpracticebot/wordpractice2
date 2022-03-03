<div align="center">
    <img src="https://i.imgur.com/zuEi84v.png" alt="Logo" width="230" height="230">
    <h1 >wordPractice v2</h1>
    <p >Practice your typing skills while having fun, compete with typists from around the world.</p>
    <a href="https://discord.gg/wordpractice">
        <img src="https://img.shields.io/discord/742960643312713738?logo=discord&style=for-the-badge"></img>
    </a>
</div>

# How to run

### 1. Clone the repository

`git clone https://github.com/wordPractice-Bot/wordpractice2`

### 2. Configuration

1. Create a `.env` file in the root directory of the repository.

2. Copy the content from `.env.example` into `.env` and fill it with the necessary information.

3. Configure any variables in `constants.py` and `icons.py`

### 3. Running

### Production

`docker compose up`

### Development

**Python 3.9+ is required**

1. Install [Poetry](https://python-poetry.org/) using `pip install poetry`

2. Install the necessary dependencies using `poetry install`

3. Activate the poetry virtual environment using `source .venv/bin/activate`

4. Type `python main.py` to run

# Formatting

[Black](https://github.com/psf/black), [isort](https://github.com/PyCQA/isort) and [Prettier](https://prettier.io/) are used for formatting
