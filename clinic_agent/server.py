"""Zero-dependency local HTTP API and web UI server."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import Settings
from .llm import build_consultant
from .service import ClinicService
from .storage import NotFoundError, Store

STATIC_ROOT = Path(__file__).parent / "static"
MAX_BODY_BYTES = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class ClinicAgentServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: ClinicService):
        super().__init__(address, RequestHandler)
        self.service = service


class RequestHandler(BaseHTTPRequestHandler):
    server: ClinicAgentServer

    @property
    def service(self) -> ClinicService:
        return self.server.service

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib method name
        self._send_empty(204, extra={"Allow": "GET, POST, OPTIONS"})

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlsplit(self.path)
            if parsed.path == "/api/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "clinic-agent",
                        "model_backend": "configured" if self.service.settings.llm_enabled else "rule_based",
                        "disclaimer": "本系统提供就医分诊参考，不提供医疗诊断或处方。",
                    },
                )
            elif parsed.path == "/api/sessions":
                query = parse_qs(parsed.query)
                try:
                    limit = min(max(int(query.get("limit", ["50"])[0]), 1), 100)
                except ValueError:
                    raise ApiError(400, "limit must be an integer")
                self._send_json(200, self.service.list_sessions(limit))
            elif parsed.path.startswith("/api/sessions/") and parsed.path.count("/") == 3:
                session_id = parsed.path.rsplit("/", 1)[1]
                self._send_json(200, self.service.get_session(session_id))
            elif parsed.path in {"", "/", "/index.html"}:
                self._send_static(STATIC_ROOT / "index.html")
            else:
                self._send_static(STATIC_ROOT / parsed.path.lstrip("/"))
        except NotFoundError:
            self._send_json(404, {"error": "session not found"})
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except FileNotFoundError:
            self._send_json(404, {"error": "not found"})
        except Exception:
            self.log_error("Unhandled request error", exc_info=True)
            self._send_json(500, {"error": "internal server error"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlsplit(self.path)
            payload = self._read_json()
            if parsed.path == "/api/sessions":
                self._send_json(201, self.service.create_session(payload))
            elif parsed.path.startswith("/api/sessions/") and parsed.path.endswith("/messages"):
                session_id = parsed.path.removesuffix("/messages").rsplit("/", 1)[1]
                self._send_json(200, self.service.handle_message(session_id, payload))
            else:
                raise ApiError(404, "not found")
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except NotFoundError:
            self._send_json(404, {"error": "session not found"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc.msg}"})
        except Exception:
            self.log_error("Unhandled request error", exc_info=True)
            self._send_json(500, {"error": "internal server error"})

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ApiError(411, "Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ApiError(400, "invalid Content-Length") from exc
        if length <= 0:
            raise ApiError(400, "request body cannot be empty")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "request body is too large")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ApiError(400, "JSON body must be an object")
        return value

    def _send_json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int, *, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self._security_headers()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_static(self, filepath: Path) -> None:
        try:
            resolved = filepath.resolve(strict=True)
            root = STATIC_ROOT.resolve(strict=True)
        except FileNotFoundError:
            raise ApiError(404, "not found") from None
        if not str(resolved).startswith(str(root) + "/") or not resolved.is_file():
            raise ApiError(404, "not found")
        body = resolved.read_bytes()
        content_type, encoding = mimetypes.guess_type(resolved)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
        for key, value in headers.items():
            self.send_header(key, value)

    def log_message(self, format: str, *args: object) -> None:
        # Keep default behavior available but avoid logging request bodies.
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def build_service(settings: Settings) -> ClinicService:
    store = Store(settings.database_path)
    consultant = build_consultant(settings)
    return ClinicService(store, consultant, settings)


def create_server(settings: Settings | None = None) -> ClinicAgentServer:
    active_settings = settings or Settings.from_env()
    return ClinicAgentServer((active_settings.host, active_settings.port), build_service(active_settings))


def run() -> None:
    settings = Settings.from_env()
    server = create_server(settings)
    print(
        f"clinic-agent 正在运行: http://{settings.host}:{settings.port} "
        f"(模式: {'模型增强' if settings.llm_enabled else '规则分诊'}, 数据: {settings.database_path})",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.service.store.close()


if __name__ == "__main__":
    run()
