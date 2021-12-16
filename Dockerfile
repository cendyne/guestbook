FROM python:3.9-slim-buster

WORKDIR /app
ADD requirements.txt /app/
RUN pip3 install -r requirements.txt

ADD bot.py guestbookdb.py supervisord.conf web.py /app/

CMD ["supervisord", "-n"]
