import sqlite3
import threading
import functools
import os
import pickle
import base64
import logging
from typing import Dict, List, Text, Tuple, Union
from dataclasses import dataclass

class ThreadDb(threading.local):
    con = None
    con: sqlite3.Connection
    cur = None
    cur: sqlite3.Cursor


localthreaddb = ThreadDb()

def create_connection() -> sqlite3.Connection:
    return sqlite3.connect(os.getenv("DB"))


def with_connection(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        con = create_connection()
        # Preserve old connection and cursor
        oldcon = localthreaddb.con
        oldcur = localthreaddb.cur
        # Set current connection as the thread connection
        localthreaddb.con = con
        localthreaddb.cur = None
        try:
            result = func(*args, **kwargs)
            con.commit()
            return result
        except Exception as e:
            con.rollback()
            raise
        finally:
            con.close()
            # Restore old connection and cursor
            localthreaddb.con = oldcon
            localthreaddb.cur = oldcur
    return wrapper


def with_cursor(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        con = localthreaddb.con
        cur = localthreaddb.cur

        if cur:
            # Rely on the upper execution to close the cursor and handle exceptions
            return func(*args, **kwargs)
        elif con:
            cur = con.cursor()
            localthreaddb.cur = cur
            try:
                return func(*args, **kwargs)
            finally:
                # SQL in general can only have one cursor at a time.
                # Because we replaced it, it is not appropriate to restore it
                # as the cursro would not be valid
                localthreaddb.cur = None
        else:
            # Create a new connection and a new cursor
            con = create_connection()
            localthreaddb.con = con
            cur = con.cursor()
            localthreaddb.cur = con.cursor()
            try:
                result = func(*args, **kwargs)
                con.commit()
                return result
            except Exception as e:
                con.rollback()
                raise
            finally:
                cur.close()
                con.close()
                # Clear both as the connection was only used for this invocation
                localthreaddb.cur = None
                localthreaddb.con = None
    return wrapper

@with_cursor
def add_user(identity: int, first_name: Text, last_name: Union[Text, None], username: Union[Text, None], icon: Union[Text, None]) -> None:
    localthreaddb.cur.execute("insert into guestbook_telegram_users (id, first_name, last_name, username, icon) values (:identity, :first_name, :last_name, :username, :icon) ", {
        "identity": identity,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "icon": icon
    })

@dataclass
class TelegramUser:
    telegram_user_id: int
    first_name: Text
    last_name: Text
    username: Text
    icon: Union[Text, None]

@with_cursor
def find_user(identity: int) -> Union[TelegramUser, None]:
    results = localthreaddb.cur.execute("select id, first_name, last_name, username, icon from guestbook_telegram_users where id = :identity", {
        "identity": identity
    }).fetchone()
    if results and len(results) > 0:
        return TelegramUser(results[0], results[1], results[2], results[3], results[4])
    return None

@with_cursor
def find_user_icon(identity: int) -> Union[Text, None]:
    results = localthreaddb.cur.execute("select icon from guestbook_telegram_users where id = :identity", {
        "identity": identity
    }).fetchone()
    if results and len(results) > 0:
        return results[0]
    return None

@with_cursor
def update_user_icon(identity: int, icon: Union[Text, None]) -> None:
    localthreaddb.cur.execute("update guestbook_telegram_users set icon = :icon where id = :identity", {
        "identity": identity,
        "icon": icon
    })

@with_cursor
def add_message(user_id: int, date: int, content: Text) -> int:
    localthreaddb.cur.execute("insert into guestbook_messages (telegram_user_id, date, content) values (:telegram_user_id, :date, :content) ", {
        "telegram_user_id": user_id,
        "date": date,
        "content": content
    })
    [identity] = localthreaddb.cur.execute("select last_insert_rowid()").fetchone()
    return identity

@with_cursor
def add_challenge(identity: Text, challenge: Text, expires: int) -> None:
    localthreaddb.cur.execute("insert into guestbook_challenge (id, challenge, expires) values (:identity, :challenge, :expires) ", {
        "identity": identity,
        "challenge": challenge,
        "expires": expires
    })

@with_cursor
def delete_old_challenges(expires: int) -> None:
    localthreaddb.cur.execute("delete from guestbook_challenge where expires <= :expires", {
        "expires": expires
    })

@with_cursor
def update_challenge_expires(identity: Text, expires: int) -> None:
    localthreaddb.cur.execute("update guestbook_challenge set expires = :expires where id = :identity", {
        "identity": identity,
        "expires": expires
    })

@with_cursor
def challenge_link_to_user(identity: Text, telegram_user_id: int) -> None:
    localthreaddb.cur.execute("update guestbook_challenge set telegram_user_id = :telegram_user_id where id = :identity and telegram_user_id is null", {
        "identity": identity,
        "telegram_user_id": telegram_user_id
    })

@dataclass
class Challenge:
    identity: Text
    challenge: Text
    expires: int
    telegram_user_id: Union[int, None]

@with_cursor
def get_challenge(identity: Text) -> Union[Challenge, None]:
    results = localthreaddb.cur.execute("select id, challenge, expires, telegram_user_id from guestbook_challenge where id = :identity", {
        "identity": identity
    }).fetchone()
    if results and len(results) > 0:
        return Challenge(results[0], results[1], results[2], results[3])
    return None

@with_cursor
def find_challenge(challenge: Text) -> Union[Text, None]:
    results = localthreaddb.cur.execute("select id from guestbook_challenge where challenge = :challenge", {
        "challenge": challenge
    }).fetchone()
    if results and len(results) > 0:
        return results[0]
    return None

@with_cursor
def find_unlinked_challenge(challenge: Text) -> Union[Text, None]:
    results = localthreaddb.cur.execute("select id from guestbook_challenge where challenge = :challenge and telegram_user_id is null", {
        "challenge": challenge
    }).fetchone()
    if results and len(results) > 0:
        return results[0]
    return None



@dataclass
class GuestbookEntry:
    date: int
    content: Text
    telegram_user_id: int
    username: Text
    first_name: Text
    last_name: Text
    icon: Union[Text, None]

@with_cursor
def read_guestbook() -> List[GuestbookEntry]:
    results = []
    db_results = localthreaddb.cur.execute("select m.date, m.content, u.id, u.username, u.first_name, u.last_name, u.icon from guestbook_messages m join guestbook_telegram_users u on m.telegram_user_id = u.id order by date desc limit 10")
    for result in db_results:
        results.append(GuestbookEntry(result[0], result[1], result[2], result[3], result[4], result[5], result[6]))
    return results

@with_connection
@with_cursor
def read_config(name: Text) -> Union[Text, None]:
    results = localthreaddb.cur.execute("select value from guestbook_config where name = :name", {"name": name}).fetchone()
    if results and len(results) > 0:
        return results[0]
    return None

@with_connection
@with_cursor
def set_config(name: Text, value: Text) -> None:
    if read_config(name) is None:
        localthreaddb.cur.execute("insert into guestbook_config(name, value) values (:name, :value)", {"name": name, "value": value})
    else:
        localthreaddb.cur.execute("update guestbook_config set value = :value where name = :name", {"name": name, "value": value})

@with_connection
@with_cursor
def init() -> None:
    cur = localthreaddb.cur

    cur.execute("create table if not exists guestbook_telegram_users (id INTEGER PRIMARY KEY, first_name text, last_name text, username text, icon text)")
    cur.execute("create index if not exists guestbook_telegram_users_username on guestbook_telegram_users (username)")
    cur.execute("create table if not exists guestbook_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_user_id integer, date integer, content text)")
    cur.execute("create index if not exists guestbook_messages_date on guestbook_messages (date)")
    cur.execute("create table if not exists guestbook_challenge(id text primary key, challenge text, expires int, telegram_user_id integer)")
    cur.execute("create index if not exists guestbook_challenge_challenge on guestbook_challenge(challenge)")
    cur.execute("create index if not exists guestbook_challenge_expires on guestbook_challenge(expires)")
    cur.execute("create table if not exists guestbook_config (name text primary key, value text)")
