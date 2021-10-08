FROM python:3.9-slim

COPY . /usr/local/tmpmail
RUN pip3 install -r /usr/local/tmpmail/requirements.txt  -i https://mirrors.ustc.edu.cn/pypi/web/simple
RUN mkdir -p /tmpmail
WORKDIR /tmpmail
