FROM python:3
MAINTAINER "Janik Luechinger janik.luechinger@uzh.ch"

COPY . /pga
WORKDIR /pga

RUN apt-get -y update && apt-get -y upgrade

# Install Docker
RUN apt install -y docker.io

# Install dependencies
RUN pip install -U pip && pip install -r requirements.txt

# Format shell script line endings to suit UNIX file endings.
RUN sed -i.bak 's/\r$//' /pga/utilities/*.sh

ENTRYPOINT [ "python", "-m", "manager" ]

# Manual image building
# docker build -t pga-cloud-manager .
# docker tag pga-cloud-manager jluech/pga-cloud-manager
# docker push jluech/pga-cloud-manager
