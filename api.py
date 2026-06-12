"""Local HTTP/JSON API client for the JUDO i-soft plus water softener.

All methods in this module are blocking and must be executed in an
executor thread (``hass.async_add_executor_job``) when called from
Home Assistant.
"""
from __future__ import annotations

import json
import logging
import re
import ssl
import time
import urllib.request
from typing import Any
from urllib.parse import quote

_LOGGER = logging.getLogger(__name__)

API_PORT = 8124
DEFAULT_TIMEOUT = 20  # seconds per HTTP request
SESSION_MAX_AGE = 600  # seconds before a proactive re-login

# Never log credentials or session tokens, even at debug level.
_REDACT_PARAMS = re.compile(r"(password|token)=[^&]*")
_REDACT_JSON_TOKEN = re.compile(r'("token"\s*:\s*")[^"]*(")')


class JudoError(Exception):
    """Base class for all JUDO API errors."""


class JudoAuthError(JudoError):
    """Raised when the device rejects the credentials."""


class JudoNotLoggedInError(JudoError):
    """Raised when the session token has expired."""


class JudoISoftPlusAPI:
    """Minimal client for the local JSON interface on port 8124."""

    def __init__(self, host: str, username: str, password: str, serial: str) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.serial = serial
        self.token: str | None = None
        self._last_login: float | None = None
        self._ssl_context: ssl.SSLContext | None = None

    # ------------------------------------------------------------------
    # Low level helpers
    # ------------------------------------------------------------------

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Create the SSL context lazily, inside the worker thread."""
        if self._ssl_context is None:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            # The device uses a self-signed certificate and only offers
            # legacy RSA cipher suites, so verification must be disabled
            # and the cipher list relaxed. Local network only.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_ciphers("RSA+AESGCM:RSA+AES:!aNULL")
            self._ssl_context = ctx
        return self._ssl_context

    def _request(self, params: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
        """Perform a GET request and return the decoded JSON payload."""
        url = f"https://{self.host}:{API_PORT}/?{params}"
        _LOGGER.debug("GET /?%s", _REDACT_PARAMS.sub(r"\1=***", params))

        req = urllib.request.Request(url)
        with urllib.request.urlopen(
            req, context=self._get_ssl_context(), timeout=timeout
        ) as resp:
            raw = resp.read().decode("utf-8")

        _LOGGER.debug("Response: %s", _REDACT_JSON_TOKEN.sub(r"\1***\2", raw))
        data = json.loads(raw)

        if isinstance(data, dict) and data.get("status") in (
            "not logged in",
            "invalid token",
        ):
            raise JudoNotLoggedInError("Session expired")

        return data

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Log in and store the session token."""
        params = (
            "group=register&command=login&msgnumber=1&name=login&"
            f"user={quote(self.username, safe='')}&"
            f"password={quote(self.password, safe='')}&role=customer"
        )
        data = self._request(params)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise JudoAuthError("Login rejected - check username/password")
        self.token = token
        self._last_login = time.monotonic()
        _LOGGER.debug("Login successful")

    def connect(self) -> None:
        """Bind the session to the device serial number."""
        params = (
            "group=register&command=connect&msgnumber=6&"
            f"token={self.token}&parameter=i-soft%20plus&"
            f"serial%20number={quote(self.serial, safe='')}"
        )
        data = self._request(params)
        if not isinstance(data, dict) or data.get("status") != "ok":
            raise JudoError(f"Connect failed: {data!r}")
        _LOGGER.debug("Connect successful")

    def _ensure_session(self) -> None:
        """Log in (again) if there is no session or it is likely stale."""
        if (
            self.token is None
            or self._last_login is None
            or time.monotonic() - self._last_login > SESSION_MAX_AGE
        ):
            self.login()
            self.connect()

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _first_int(value: Any) -> Any:
        """Return the first integer of a space separated string."""
        if not isinstance(value, str):
            return value
        try:
            parts = [int(x) for x in value.split()]
        except ValueError:
            _LOGGER.error("Unexpected water value format: %r", value)
            return None
        return parts[0] if parts else None

    @staticmethod
    def _sum_ints(value: Any) -> Any:
        """Return the sum of all integers of a space separated string."""
        if not isinstance(value, str):
            return value
        try:
            return sum(int(x) for x in value.split())
        except ValueError:
            _LOGGER.error("Unexpected water value format: %r", value)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_value(self, group: str, command: str, msg: int = 1) -> Any:
        """Read a single value; retries once after a re-login on failure.

        ``group`` and ``command`` are expected to be pre-URL-encoded
        (e.g. ``water%20total``) to match the device's wire format.
        """
        self._ensure_session()

        try:
            data = self._read_raw(group, command, msg)
        except JudoNotLoggedInError:
            _LOGGER.info(
                "Session expired while reading %s/%s - re-login", group, command
            )
            self.login()
            self.connect()
            data = self._read_raw(group, command, msg)
        except OSError as err:
            # Timeouts, TLS and connection errors -> one retry after re-login.
            _LOGGER.warning(
                "Connection problem reading %s/%s (%s) - retrying after re-login",
                group,
                command,
                err,
            )
            self.login()
            self.connect()
            data = self._read_raw(group, command, msg)

        value = data.get("data") if isinstance(data, dict) else None

        if command in ("water%20total", "water%20current"):
            return self._first_int(value)
        if command in (
            "water%20daily",
            "water%20weekly",
            "water%20monthly",
            "water%20yearly",
        ):
            return self._sum_ints(value)
        return value

    def _read_raw(self, group: str, command: str, msg: int) -> Any:
        params = f"group={group}&command={command}&msgnumber={msg}&token={self.token}"
        return self._request(params)
