import uuid
import secrets
import time
import os
import html
from fastapi import FastAPI, Response, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

import guestbookdb

load_dotenv()

app = FastAPI()
# uvicorn web:app --reload --port $PORT

letters = "cdefhjkmnprtvwxy2345689"

icon_path = os.environ["ICON_PATH"]

if not os.path.exists(icon_path):
    os.makedirs(icon_path)

app.mount("/icons", StaticFiles(directory=icon_path), name="icons")



@app.get("/", response_class=HTMLResponse)
@guestbookdb.with_connection
def read_root(request: Request, response: Response):
    identity = None
    session = None
    if "s" in request.cookies:
        identity = request.cookies["s"]
        session = guestbookdb.get_challenge(identity)
    if not session:
        identity = str(uuid.uuid4())
        response.set_cookie(key="s", value=identity)
        # By default expire in 1 day
        expires = int(time.time() + 60 * 60 * 24)
        challenge = ""
        for i in range(8):
            challenge += secrets.choice(letters).upper()
        guestbookdb.add_challenge(identity, challenge, expires)
        session = guestbookdb.get_challenge(identity)

    body = "<!DOCTYPE html><html><head><title>Silly Snake Auth</title></head><body>\n"
    if session.telegram_user_id:
        guestbook_user = guestbookdb.find_user(session.telegram_user_id)
        body += "<h1>Hey " + html.escape(guestbook_user.first_name) + "</h1>\n"
    else:
        body += "<h1>Sign in Please!</h1>"
        bot_username = guestbookdb.read_config("username") 
        body += "<h2><a href=\"https://t.me/" + bot_username + "?start=hey\" target=\"_blank\">Message @" + bot_username + "</a></h2>\n"
        body += "<p>Use the challenge code: <strong>" + html.escape(session.challenge) + "</strong>. Then refresh!</p>\n"
        body += "<hr />"
    body += "<center>"
    if session.telegram_user_id:
        body += "<form action=\"/message\" method=\"post\"><input type=\"text\" name=\"message\" placeholder=\"Message here\" /><input type=\"submit\" /></form>\n"
    body +="<table><tr><th></th><th>Name</th><th>Message</th></tr>\n"
    messages = guestbookdb.read_guestbook()
    for message in messages:
        body += "<tr><td>"
        if message.icon:
            body += "<img src=\"icons/" + message.icon + "\" />"
        body += "</td><td>" + html.escape(message.first_name) + "</td><td>" + html.escape(message.content) + "</td></tr>\n"
    body += "</table>\n"
    body += "</center>\n</body></html>"
    return body


@app.get("/not-auth", response_class=HTMLResponse)
@guestbookdb.with_connection
def not_authed():
    return """
<h1>You are not authenticated!</h1><p><a href=\"/">Go back</a></p>
    """

@app.post("/message", response_class=RedirectResponse)
@guestbookdb.with_connection
def recv_message(request: Request, message: str = Form(...)):
    if "s" in request.cookies:
        identity = request.cookies["s"]
        session = guestbookdb.get_challenge(identity)
    if not session or not session.telegram_user_id:
        return RedirectResponse("/not-auth", status_code=301)
    guestbookdb.add_message(session.telegram_user_id, int(time.time()), message)
    return RedirectResponse("/", status_code=301)
