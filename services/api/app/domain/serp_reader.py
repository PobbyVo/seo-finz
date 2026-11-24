"""Đọc có giới hạn, DNS pinning và kiểm từng redirect; không gửi credentials."""

from __future__ import annotations
from html.parser import HTMLParser
import http.client
import socket
import ssl
from urllib.parse import urljoin
from app.security.ssrf import resolve_public_web_url


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading = None
        self.title = []
        self.h2 = []
        self.text = []
        self.skip = 0
        self.updated = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "nav", "footer"):
            self.skip += 1
        if tag in ("title", "h2"):
            self.heading = tag
        if tag == "meta" and attrs.get("property") in (
            "article:modified_time",
            "article:published_time",
        ):
            self.updated.append(attrs.get("content", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer"):
            self.skip = max(0, self.skip - 1)
        if tag in ("title", "h2"):
            self.heading = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.heading == "title":
            self.title.append(data.strip())
        if self.heading == "h2":
            self.h2.append(data.strip())
        self.text.append(data.strip())


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, timeout=10, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        sock = socket.create_connection((self.ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def read_article(url):
    import re

    current = url
    try:
        for _ in range(4):
            host, ip, path = resolve_public_web_url(current)
            connection = PinnedHTTPS(host, ip)
            try:
                connection.request(
                    "GET",
                    path,
                    headers={
                        "User-Agent": "FinZResearch/2.0",
                        "Accept": "text/html",
                        "Accept-Encoding": "identity",
                    },
                )
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    current = urljoin(current, response.getheader("Location") or "")
                    continue
                if response.status != 200 or "text/html" not in (
                    response.getheader("Content-Type") or ""
                ):
                    raise ValueError("Không phải trang HTML có thể đọc.")
                raw = response.read(1000001)
                if len(raw) > 1000000:
                    raise ValueError("Trang vượt giới hạn 1MB.")
            finally:
                connection.close()
            parser = ArticleParser()
            parser.feed(raw.decode("utf-8", errors="replace"))
            text = " ".join(parser.text)
            return {
                "url": url,
                "final_url": current,
                "read_status": "READ",
                "title": " ".join(parser.title),
                "h2": parser.h2,
                "word_count": len(text.split()),
                "legal_mentions": re.findall(
                    r"(?:Luật|Nghị định|Thông tư|Nghị quyết)[^.\n]{0,180}", text
                ),
                "updated_at": parser.updated,
                "excerpt": text[:18000],
            }
        raise ValueError("Quá nhiều chuyển hướng.")
    except (ValueError, OSError, http.client.HTTPException) as exc:
        return {
            "url": url,
            "read_status": "UNREADABLE",
            "message": "Không đọc được: " + str(exc),
        }
