FROM python:3.5.2

RUN apt-get clean && \
    apt-get update && \
    apt-get install -y \
        apt-utils \
        python-dev \
        vim

COPY requirements.txt /code/requirements.txt
RUN pip install -r /code/requirements.txt

COPY main.py /code/
COPY phrases.py /code/
COPY token.txt /code/

CMD python /code/main.py
