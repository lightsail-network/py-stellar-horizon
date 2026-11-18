"""An HTTP server on localhost that streams events the way a test scripts them.

A mock transport hands the client a whole body at once and cannot show what a socket
does: when bytes arrive, how a reset or a silent peer surfaces, and whether closing a
stream closes its connection. This server runs in a thread and writes each event to
the socket as soon as the test's script says so, chunked, as Horizon does.
"""

import contextlib
import socket
import struct
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Self, cast

WAIT = 5.0
"""Seconds the server waits for the client before it gives up on a test."""


class Connection:
    """One connection the server is answering, as the script sees it."""

    def __init__(self, handler: "_Handler") -> None:
        self._handler = handler

    def send(self, *events: str) -> None:
        """Write each event, in full and at once, as one chunk."""
        for event in events:
            data = (event + "\n\n").encode()
            self._handler.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
            self._handler.wfile.flush()

    def send_raw(self, data: str) -> None:
        """Write a chunk that need not end an event."""
        raw = data.encode()
        self._handler.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
        self._handler.wfile.flush()

    def end(self) -> None:
        """End the body, as a server does that stops without a `close` event."""
        self._handler.wfile.write(b"0\r\n\r\n")
        self._handler.wfile.flush()

    def reset(self) -> None:
        """Abort the connection with a TCP reset."""
        sock = self._handler.connection
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        sock.close()

    def wait(self, event: threading.Event) -> None:
        """Wait until the test sets `event`; note a failure if it never does."""
        if not event.wait(WAIT):
            self._handler.local.failures.append("the test never let the server go on")

    def wait_until_released(self) -> bool:
        """Wait until the client closes the connection, and tell whether it did."""
        sock: socket.socket = self._handler.connection
        sock.settimeout(WAIT)
        try:
            released = sock.recv(1) == b""
        except TimeoutError:
            released = False
        except OSError:
            released = True
        if released:
            self._handler.local.released.set()
        return released


Answer = Callable[[Connection], None]


class LocalHorizon:
    """A server on a free port of localhost that answers with event streams.

    Each request takes the next answer of the script; the last one is repeated. An
    answer is a function that writes to the connection.
    """

    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.requests: list[str] = []
        """The path and query of each request, as sent."""
        self.failures: list[str] = []
        """What went wrong on the server's side; a test checks that it is empty."""
        self.released = threading.Event()
        """Set when a client closed a connection that the server waited on."""
        self._server = _Server(self)
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(0.01,), daemon=True
        )

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def answer(self) -> Answer:
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(WAIT)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, local: LocalHorizon) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.local = local


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def local(self) -> LocalHorizon:
        return cast("_Server", self.server).local

    def do_GET(self) -> None:
        self.local.requests.append(self.path)
        answer = self.local.answer()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.close_connection = True
        # The client can go away, which some scripts expect.
        with contextlib.suppress(OSError):
            answer(Connection(self))

    def finish(self) -> None:
        # The script may have reset the connection.
        with contextlib.suppress(OSError):
            super().finish()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass
