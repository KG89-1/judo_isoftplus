import json
import ssl
import urllib.request
import logging
import time

_LOGGER = logging.getLogger(__name__)


class JudoNotLoggedInError(Exception):
    pass


class JudoISoftPlusAPI:
    def __init__(self, host, username, password, serial):
        self.host = host
        self.username = username
        self.password = password
        self.serial = serial
        self.token = None
        self._last_login = None

        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.ssl_context.set_ciphers("RSA+AESGCM:RSA+AES:!aNULL")

    def _url(self, params: str):
        url = f"https://{self.host}:8124/?{params}"
        _LOGGER.debug("API URL constructed: %s", url)
        return url

    def _get(self, url: str, timeout: int = 20):
        _LOGGER.debug("HTTP GET request: %s", url)

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                _LOGGER.debug("HTTP response raw: %s", raw)

                data = json.loads(raw)

                if isinstance(data, dict) and "status" in data:
                    if data["status"] in ("not logged in", "invalid token"):
                        _LOGGER.warning("JUDO API login expired")
                        raise JudoNotLoggedInError("Session expired")

                return data

        except JudoNotLoggedInError:
            raise

        except Exception as e:
            _LOGGER.error("HTTP request failed: %s", e)
            raise

    # -----------------------------------------------------------------
    # Parsing helpers
    # -----------------------------------------------------------------

    def _extract_raw_water_liters(self, value):
        if not isinstance(value, str):
            return value
        try:
            parts = [int(x) for x in value.split()]
            return parts[0] if parts else None
        except Exception as e:
            _LOGGER.error("Failed to extract raw water from '%s': %s", value, e)
            return None

    def _sum_water_values(self, value):
        if not isinstance(value, str):
            return value
        try:
            parts = [int(x) for x in value.split()]
            return sum(parts)
        except Exception as e:
            _LOGGER.error("Failed to sum water values '%s': %s", value, e)
            return None

    # -----------------------------------------------------------------
    # API workflow
    # -----------------------------------------------------------------

    def login(self):
        params = (
            "group=register&command=login&msgnumber=1&name=login&"
            f"user={self.username}&password={self.password}&role=customer"
        )
        data = self._get(self._url(params))
        self.token = data.get("token")
        if not self.token:
            raise RuntimeError("Login failed – no token received")
        self._last_login = time.monotonic()
        _LOGGER.info("JUDO login successful, token obtained")

    def connect(self):
        params = (
            "group=register&command=connect&msgnumber=6&"
            f"token={self.token}&parameter=i-soft%20plus&serial%20number={self.serial}"
        )
        data = self._get(self._url(params))
        if data.get("status") != "ok":
            raise RuntimeError("Connect failed")
        _LOGGER.info("JUDO connect successful")

    def _ensure_session(self):
        """Re-login proactively if session is likely stale (>10 min)."""
        if self.token is None or self._last_login is None:
            self.login()
            self.connect()
            return

        elapsed = time.monotonic() - self._last_login
        if elapsed > 600:  # 10 minutes
            _LOGGER.info(
                "Session age %.0fs – proactive re-login", elapsed
            )
            self.login()
            self.connect()

    # -----------------------------------------------------------------
    # Value reading with robust retry
    # -----------------------------------------------------------------

    def read_value(self, group, command, msg=1):
        self._ensure_session()

        params = f"group={group}&command={command}&msgnumber={msg}&token={self.token}"

        try:
            data = self._get(self._url(params))
        except JudoNotLoggedInError:
            _LOGGER.info("Session expired on read – re-login")
            self.login()
            self.connect()
            params = f"group={group}&command={command}&msgnumber={msg}&token={self.token}"
            data = self._get(self._url(params))
        except (TimeoutError, OSError) as e:
            # Timeout or connection error → re-login and retry once
            _LOGGER.warning(
                "Timeout/connection error reading %s/%s: %s – retrying after re-login",
                group, command, e,
            )
            self.login()
            self.connect()
            params = f"group={group}&command={command}&msgnumber={msg}&token={self.token}"
            data = self._get(self._url(params))

        value = data.get("data")

        if command == "water%20total":
            return self._extract_raw_water_liters(value)

        if command == "water%20current":
            return self._extract_raw_water_liters(value)

        if command in [
            "water%20daily",
            "water%20weekly",
            "water%20monthly",
            "water%20yearly",
        ]:
            return self._sum_water_values(value)

        return value
