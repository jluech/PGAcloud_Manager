FROM python:3
LABEL maintainer="Janik Luechinger janik.luechinger@uzh.ch"

COPY . /app

WORKDIR /app

RUN pip install -U pip && pip install -r requirements.txt

CMD [ "python", "-m", "manager" ]
