"""Smoke test for a deployed stack (Phase 8): `uv run poe smoke-public --url https://HOST`.

Checks, in order: health, the app page and its security headers, the HTTP-to-HTTPS redirect
(https URLs only), one-click demo sign-in, and the session. `--ask` also asks one question
through the streaming endpoint: in live mode that is a paid model call (about $0.0007 with
gpt-6-luna). `--expect-status 429` or `503` instead checks that the question is refused (daily
budget cap, kill switch). Prints status lines only, never a cookie or a secret.

Standard library only, so it also runs on the server with plain `python3`.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from http.cookiejar import CookieJar
from urllib.parse import urlsplit

DEMO_QUESTION = "What was net revenue by sales channel in Q1 2026?"
SECURITY_HEADERS = [
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Smoke:
    def __init__(self, base: str, timeout: float):
        self.base = base.rstrip("/")
        self.https = urlsplit(self.base).scheme == "https"
        self.timeout = timeout
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.failed = False

    def result(self, ok: bool, name: str, detail: str = "") -> bool:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
        self.failed |= not ok
        return ok

    def request(self, path: str, body: dict | None = None, accept: str = "application/json"):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Accept": accept})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return self.opener.open(req, timeout=self.timeout)

    def get_json(self, path: str, body: dict | None = None) -> dict:
        with self.request(path, body) as resp:
            return json.load(resp)

    def health(self) -> bool:
        h = self.get_json("/api/health")
        detail = f"status={h['status']} mode={h['mode']} live_mode_enabled={h['live_mode_enabled']}"
        return self.result(h["status"] == "ok", "health", detail)

    def page(self) -> bool:
        with self.request("/", accept="text/html") as resp:
            html = resp.read().decode()
            headers = resp.headers
        self.result('<div id="root">' in html, "app page")
        wanted = SECURITY_HEADERS + (["Strict-Transport-Security"] if self.https else [])
        missing = [h for h in wanted if not headers.get(h)]
        return self.result(not missing, "security headers", f"missing {missing}" if missing else "")

    def redirect(self) -> bool:
        host = urlsplit(self.base).netloc
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(f"http://{host}/", timeout=self.timeout)
            return self.result(False, "HTTP redirects to HTTPS", "got 200 over plain HTTP")
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location", "")
            ok = e.code in (301, 302, 307, 308) and location.startswith(f"https://{host}")
            return self.result(ok, "HTTP redirects to HTTPS", f"{e.code} -> {location}")

    def sign_in(self) -> bool:
        options = self.get_json("/api/auth/options")
        if not self.result(options["demo_login_enabled"], "demo sign-in offered"):
            return False
        with self.request("/api/auth/demo", {"user": "analyst"}) as resp:
            cookie = resp.headers.get("Set-Cookie", "")
        flags = cookie.lower()
        ok = "httponly" in flags and ("secure" in flags or not self.https)
        self.result(ok, "session cookie flags", "HttpOnly" + (", Secure" if self.https else ""))
        me = self.get_json("/api/me")
        return self.result(me.get("user_id") == "analyst@demo", "signed in", me.get("role", ""))

    def ask(self, question: str, expect_status: int | None) -> bool:
        try:
            with self.request(
                "/api/ask/stream", {"question": question}, accept="text/event-stream"
            ) as resp:
                events = parse_sse(line.decode() for line in resp)
        except urllib.error.HTTPError as e:
            try:
                code = json.load(e)["detail"]["code"]
            except (ValueError, KeyError, TypeError):
                code = "(no JSON error body)"
            return self.result(expect_status == e.code, "ask refused", f"HTTP {e.code} {code}")
        if expect_status is not None:
            return self.result(False, "ask refused", f"expected HTTP {expect_status}, got 200")
        return self.check_events(events)

    def check_events(self, events: list[tuple[str, dict]]) -> bool:
        kinds = [kind for kind, _ in events]
        data = dict(events)
        self.result(
            "step" in kinds and "sql" in kinds and "rows" in kinds, "streamed steps, SQL, rows"
        )
        if "error" in data:
            return self.result(False, "answer", data["error"].get("code", ""))
        answer, done = data.get("answer", {}), data.get("done", {})
        usage = done.get("usage", {})
        self.result(answer.get("status") == "answered", "answer", answer.get("status", "missing"))
        detail = (
            f"rows={data.get('rows', {}).get('row_count')} keyless={usage.get('keyless')} "
            f"llm_calls={usage.get('llm_calls')} cost_usd={usage.get('cost_usd')} "
            f"latency_ms={usage.get('latency_ms')}"
        )
        return self.result(bool(done), "run finished", detail)


def parse_sse(lines: Iterable[str]) -> list[tuple[str, dict]]:
    """Parse server-sent events (`event:` + `data:` lines, blank line between) into pairs."""
    events, kind, data = [], None, []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("event:"):
            kind = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif not line and kind:
            events.append((kind, json.loads("\n".join(data)) if data else {}))
            kind, data = None, []
    if kind:
        events.append((kind, json.loads("\n".join(data)) if data else {}))
    return events


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", required=True, help="base URL, for example https://HOST")
    p.add_argument("--ask", action="store_true", help="also ask a question (paid in live mode)")
    p.add_argument("--question", default=DEMO_QUESTION)
    p.add_argument("--expect-status", type=int, choices=[429, 503], help="the ask must be refused")
    p.add_argument("--timeout", type=float, default=90.0)
    args = p.parse_args(argv)

    s = Smoke(args.url, args.timeout)
    try:
        ready = s.health() and s.page() and (not s.https or s.redirect()) and s.sign_in()
        if ready and (args.ask or args.expect_status):
            s.ask(args.question, args.expect_status)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        s.result(False, "request", f"{type(e).__name__}: {e}")
    print("smoke test " + ("FAILED" if s.failed else "passed"))
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())
