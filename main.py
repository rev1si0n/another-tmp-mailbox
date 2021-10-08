#!/usr/bin/python3
import os
import re
import json
import time
import logging
import asyncio
import datetime
import functools
import traceback
import threading

from uuid import uuid4

import mailparser

import tornado.web
import tornado.ioloop

from tornado.web import HTTPError
from tornado.options import define, options

from peewee import *
from playhouse.shortcuts import model_to_dict

import aiosmtpd.smtp
from aiosmtpd.controller import Controller


database = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = database
    def to_dict(self, **kwargs):
        ret = model_to_dict(self, **kwargs)
        return ret


class User(BaseModel):
    def dict(self):
        fmt = "%Y-%m-%d %H:%M:%S"
        item = self.to_dict(exclude=[User.mail, User.create_time])
        return item
    uuid                = CharField(max_length=32, unique=True)
    create_time         = DateTimeField(default=datetime.datetime.now)
    last_active         = BigIntegerField(default=time.time)


class Mail(BaseModel):
    def dict(self, exclude=[]):
        fmt = "%Y-%m-%d %H:%M:%S"
        item = self.to_dict(exclude=[Mail.user, *exclude])
        item["create_time"] = self.create_time.strftime(fmt)
        item["send_time"] = self.send_time.strftime(fmt)
        return item
    user                = ForeignKeyField(User, backref="mail")

    subject             = CharField(max_length=512)
    content             = CharField(max_length=65535)
    html_content        = CharField(max_length=65535)
    sender              = CharField(max_length=256)

    create_time         = DateTimeField(default=datetime.datetime.now)
    send_time           = DateTimeField()


class SmtpdHandler(object):
    domains = []
    async def handle_DATA(self, server, session, envelope):
        mail = mailparser.parse_from_bytes(envelope.content)
        mm = dict(subject=mail.subject)
        mm["content"]      = "".join(mail.text_plain)
        mm["html_content"] = "".join(mail.text_html)
        mm["sender"]    = envelope.mail_from
        mm["send_time"] = mail.date

        Mail.create(**mm, user=envelope.rcpt_tos[0])
        return "250 Message accepted for delivery"

    async def handle_RCPT(self, server, session, envelope,
                          address, rcpt_options):
        addr = re.search("^(?P<uuid>[a-f0-9]{8})@(?P<domain>[a-z0-9_\.-]+)$",
                                    address)
        if addr is None:
            return "501 Malformed Address"
        if addr["domain"] not in self.domains:
            return "501 Domain Not Handled"
        user = User.get_or_none(uuid=addr["uuid"])
        if user is None:
            return "510 Addresss Does Not Exist"
        envelope.rcpt_tos.append(user)
        return "250 OK"


class BaseHTTPService(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    def is_valid_uuid(self, uuid):
        valid = re.search("^([a-f0-9]{8})$", uuid)
        return valid is not None

    def write_error(self, *args, **kwargs):
        _, err, _ = kwargs["exc_info"]
        status = getattr(err, "status_code", 500)
        self.set_status(status)
        self.write({"code": status})
        self.finish()


class SmtpMailBoxHandler(BaseHTTPService):
    def delete(self, uuid):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        Mail.delete().where(Mail.user==user).execute()

    def get(self, uuid):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        mail = user.mail.select().order_by(Mail.send_time.desc()
                                ).limit(32)
        ret = [item.dict(exclude=[Mail.content, \
                Mail.html_content]) for item in mail]
        self.finish(json.dumps(ret))


class SmtpMailBoxDetailHandler(BaseHTTPService):
    def get(self, uuid, mail_id):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        mail = Mail.get_or_none(user=user,
                                id=mail_id)
        mail = mail.dict() if mail else {}
        self.finish(mail)


class SmtpMailBoxIframeLoadHandler(BaseHTTPService):
    def set_default_headers(self):
        self.set_header("Content-Type", "text/html; charset=UTF-8")

    def get(self, uuid, mail_id):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        mail = Mail.get_or_none(user=user,
                                id=mail_id)
        mail = mail.dict() if mail else {}
        html = mail.get("html_content", "") \
                            or mail.get("content")
        html = html.strip()
        self.write('<base target="_blank">')
        self.write('<meta name="referrer" content="none">')
        if not html.startswith("<"):
            html = '<pre>%s</pre>' % html
        self.finish(html)


class SmtpMailBoxIframeNewtabHandler(BaseHTTPService):
    def set_default_headers(self):
        self.set_header("Content-Type", "text/html; charset=UTF-8")

    def get(self, uuid, mail_id):
        src = "/mail/{}/{}/iframe".format(uuid, mail_id)
        self.render("iframe.html", src=src)


class SmtpMailBoxRssHandler(BaseHTTPService):
    def set_default_headers(self):
        self.set_header("Content-Type", "text/xml; charset=UTF-8")

    def initialize(self, domain):
        self.domain = domain

    def get(self, uuid):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        user.last_active = time.time()
        user.save() # prevent schd auto remove
        tz = time.strftime("%z")
        self.render("rss.xml", tz=tz, domain=self.domain,
                user=user, server=self.request.headers["Host"])


class SmtpUserHandler(BaseHTTPService):
    def delete(self, uuid):
        user = User.get_or_none(uuid=uuid)
        if user is None:
            raise HTTPError(404)
        user.delete_instance(True)
        self.clear_cookie("uuid")

    def post(self, uuid):
        uuid = uuid or self.get_cookie("uuid", "")
        user = {"uuid": uuid or uuid4().hex[::4]}
        if not self.is_valid_uuid(user["uuid"]):
            raise HTTPError(400)
        user, _ = User.get_or_create(uuid=user["uuid"],
                                     defaults=user)
        user.last_active = time.time()
        user.save()
        self.set_cookie("uuid", user.uuid,
                            expires_days=2**16)
        self.finish(user.dict())


class SmtpIndexHandler(BaseHTTPService):
    def set_default_headers(self):
        self.set_header("Content-Type", "text/html")

    def initialize(self, domain):
        self.domain = domain

    def get(self):
        self.render("index.html",
                    domain=self.domain)


class SmtpIntroHandler(BaseHTTPService):
    def set_default_headers(self):
        self.set_header("Content-Type", "text/html")

    def get(self):
        self.render("intro.html")


def schd_cleaner(seconds, interval):
    logger = logging.getLogger("cleaner")
    while True:
        time.sleep(interval)
        logger.info("user clean task is running")
        for user in User.select().where(User.last_active < (time.time() - seconds)):
            logger.warning("clean user data: %s" % user.uuid)
            user.delete_instance(True)


if __name__ == "__main__":
    define("domain", type=str)
    define("database", type=str, default="mail.db")
    define("listen", type=str, default="0.0.0.0")
    define("port", type=int, default=8888)
    options.parse_command_line()

    tornado.ioloop.IOLoop.configure("tornado.platform.asyncio.AsyncIOLoop")
    database.init(options.database, pragmas={"locking_mode": "NORMAL",
                                             "journal_mod": "wal",
                                             "synchronous": "OFF"})
    templates = os.path.join(os.path.dirname(__file__), "templates")
    statics = os.path.join(os.path.dirname(__file__), "static")
    server = tornado.web.Application(
    [
        ("/intro", SmtpIntroHandler),
        ("/favicon.ico", tornado.web.StaticFileHandler, dict(url="/static/favicon.ico",
                                            permanent=False)),
        ("/", SmtpIndexHandler, dict(domain=options.domain)),
        ("/mail/([a-f0-9]{8})/(\d+)/iframe", SmtpMailBoxIframeLoadHandler),
        ("/mail/([a-f0-9]{8})/(\d+)/show", SmtpMailBoxIframeNewtabHandler),
        ("/mail/([a-f0-9]{8})/(\d+)", SmtpMailBoxDetailHandler),
        ("/mail/([a-f0-9]{8})/rss", SmtpMailBoxRssHandler,
                            dict(domain=options.domain)),
        ("/mail/([a-f0-9]{8})", SmtpMailBoxHandler),
        ("/user/([a-f0-9]{8})?", SmtpUserHandler),
    ],
    template_path=templates,
    static_path=statics)

    server.listen(options.port, address=options.listen,
                  xheaders=True)

    SmtpdHandler.domains.append(options.domain)
    smtp = Controller(SmtpdHandler(), hostname="0.0.0.0",
                      port=25)
    smtp.start()

    User.create_table()
    Mail.create_table()

    cleaner = threading.Thread(target=schd_cleaner, args=(7*86400, 600))
    cleaner.start()

    loop = asyncio.get_event_loop()
    loop.run_forever()
