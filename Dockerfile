FROM python:3.9 

# Creating the working directory
WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Installing dependencies
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

COPY . .
CMD ["python", "main.py"]