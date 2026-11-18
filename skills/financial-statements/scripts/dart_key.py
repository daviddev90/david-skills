#!/usr/bin/env python3
"""Local OpenDART key setup and authenticated requests."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from credential_store import CredentialError, get_key, save_key

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "dart-setup.html"
KEY_NAME = "DART_API_KEY"
API_ROOT = "https://opendart.fss.or.kr/api/"
KEY_PATTERN = re.compile(r"[A-Za-z0-9]{40}")
READY = "DART_KEY_READY"
PUBLIC = "DART_KEY_PUBLIC"
SETUP_NEEDED = "DART_KEY_SETUP_NEEDED"


def public_choice_path():
    base = os.environ.get("LOCALAPPDATA" if sys.platform == "win32" else "XDG_CONFIG_HOME")
    config = Path(base) if base else Path.home() / ".config"
    return config / "aisy" / "financial-statements" / "public-only"


def key_status():
    key = os.environ.get(KEY_NAME, "").strip()
    if key:
        return READY, key
    if public_choice_path().is_file():
        return PUBLIC, None
    try:
        key = get_key()
    except CredentialError:
        key = None
    return (READY, key) if key else (SETUP_NEEDED, None)


def exchange_request(arguments):
    helper = Path.home() / ".local" / "bin" / "with-secret"
    if os.environ.get("AISY_DART_EXCHANGE_ACTIVE") or not helper.is_file():
        return None
    try:
        result = subprocess.run(
            [str(helper), KEY_NAME, "--", sys.executable, "-B", str(Path(__file__).resolve()), *arguments],
            env={**os.environ, "AISY_DART_EXCHANGE_ACTIVE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def request_api(endpoint, params, key):
    query = urlencode({"crtfc_key": key, **params})
    request = Request(API_ROOT + endpoint + "?" + query, headers={"User-Agent": "AISY financial-statements"})
    with build_opener(NoRedirect).open(request, timeout=12) as result:
        return result.read()


def validate_key(key):
    if not KEY_PATTERN.fullmatch(key):
        return "OpenDART에서 복사한 40자리 키를 다시 붙여넣어 주세요."
    try:
        result = json.loads(request_api("company.json", {"corp_code": "00126380"}, key))
    except (OSError, ValueError, HTTPError, URLError):
        return "OpenDART에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요."
    if result.get("status") in {"010", "011", "012", "901"}:
        return "OpenDART에서 이 키를 사용할 수 없습니다. 인증키 관리에서 키 상태를 확인해 주세요."
    if result.get("status") != "000":
        return "OpenDART에서 키를 확인하지 못했습니다. 잠시 뒤 다시 시도해 주세요."
    return None


class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def setup(self):
        self.request.settimeout(6)
        super().setup()

    def valid_page(self):
        return self.path == self.server.page_path and self.headers.get("Host") == self.server.host_header

    def send_page(self, state, message="", code=200):
        markup = self.server.template.replace("{{STATE}}", state).replace("{{ERROR}}", html.escape(message))
        body = markup.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.valid_page():
            self.send_page("entry")
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.valid_page():
            self.send_error(404)
            return
        if self.headers.get("Origin") not in {None, self.server.origin}:
            self.send_error(403)
            return
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            self.send_error(415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 1024:
                raise ValueError
            form = parse_qs(self.rfile.read(length).decode("ascii"), max_num_fields=2)
        except (OSError, ValueError):
            self.send_error(400)
            return

        action = form.get("action")
        if action == ["skip"]:
            flag = public_choice_path()
            try:
                flag.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                flag.touch(mode=0o600)
            except OSError:
                self.send_page("error", "선택을 저장하지 못했습니다. 다시 시도해 주세요.", 503)
                return
            self.server.result = PUBLIC
            self.send_page("public")
            return
        if action != ["save"]:
            self.send_error(400)
            return

        keys = form.get("key", [])
        key = keys[0].strip() if len(keys) == 1 else ""
        message = validate_key(key)
        if message:
            self.send_page("error", message, 422)
            return
        try:
            save_key(key)
            if get_key() != key:
                raise CredentialError()
            public_choice_path().unlink(missing_ok=True)
        except (CredentialError, OSError):
            message = "키를 저장하지 못했습니다. 다시 시도하거나 공개 DART로 조회해 주세요."
            if sys.platform == "darwin":
                message = "키를 저장하지 못했습니다. 키체인이 잠겼다면 ‘키체인 접근’에서 로그인 키체인을 잠금 해제한 뒤 다시 저장해 주세요."
            self.send_page("error", message, 503)
            return
        self.server.result = READY
        self.send_page("saved")


def setup_page(timeout, emit_result=True):
    markup = TEMPLATE.read_text(encoding="utf-8")
    with HTTPServer(("127.0.0.1", 0), SetupHandler) as server:
        server.template = markup
        server.host_header = f"127.0.0.1:{server.server_port}"
        server.origin = f"http://{server.host_header}"
        server.page_path = "/" + secrets.token_urlsafe(24)
        server.result = None
        print(f"DART_SETUP_URL {server.origin}{server.page_path}", flush=True)
        deadline = monotonic() + timeout
        while server.result is None and monotonic() < deadline:
            server.timeout = min(1, max(0, deadline - monotonic()))
            server.handle_request()
        result = server.result or "DART_SETUP_EXPIRED"
        if emit_result:
            print(result, flush=True)
    return 0 if result != "DART_SETUP_EXPIRED" else 4


def start_setup(timeout):
    if sys.platform == "win32":
        options = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "setup", "--serve", "--timeout", str(timeout)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            **options,
        )
        with process.stdout:
            link = process.stdout.readline().strip()
    except OSError:
        link = ""
    if not link.startswith("DART_SETUP_URL http://127.0.0.1:"):
        print("DART_SETUP_UNAVAILABLE")
        return 1
    print(link, flush=True)
    return 0


def fetch(endpoint, arguments, parser):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*\.(json|xml)", endpoint):
        parser.error("OpenDART API 이름을 입력하세요.")
    params = {}
    for argument in arguments:
        name, sep, value = argument.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name.lower() == "crtfc_key":
            parser.error("조회 조건만 이름=값 형식으로 입력하세요.")
        params[name] = value

    status, key = key_status()
    if not key:
        if status == SETUP_NEEDED:
            output = exchange_request(["fetch", endpoint, *arguments])
            if output is not None:
                sys.stdout.buffer.write(output)
                return 0
        print(status, file=sys.stderr)
        return 3
    try:
        body = request_api(endpoint, params, key)
    except (OSError, HTTPError, URLError):
        print("OpenDART 요청에 실패했습니다.", file=sys.stderr)
        return 1
    if body.startswith(b"PK\x03\x04"):
        sys.stdout.buffer.write(body)
    else:
        sys.stdout.buffer.write(body.replace(key.encode("utf-8"), b"[REDACTED]"))
    return 0


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    for name in ("first-use", "setup"):
        command = commands.add_parser(name)
        command.add_argument("--timeout", type=int, default=600)
        if name == "setup":
            command.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    request = commands.add_parser("fetch")
    request.add_argument("endpoint")
    request.add_argument("params", nargs="*")
    args = parser.parse_args()
    if args.command == "fetch":
        return fetch(args.endpoint, args.params, parser)
    if args.command != "setup":
        status, _ = key_status()
        if status == SETUP_NEEDED:
            result = exchange_request(["status"])
            if result is not None and result.strip() == READY.encode():
                status = READY
        if args.command == "status" or status != SETUP_NEEDED:
            print(status)
            return 0
    if not 1 <= args.timeout <= 1800:
        parser.error("설정 페이지 대기 시간은 1초에서 30분 사이여야 합니다.")
    if args.command == "setup" and args.serve:
        return setup_page(args.timeout, emit_result=False)
    return start_setup(args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
