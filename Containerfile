FROM python:latest

LABEL maintainer="sheruost@duck.com"

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["python3", "main.py"]
