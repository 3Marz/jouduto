"""Turso Cloud connection settings for Jouduto.

Jouduto keeps one database per fiscal year, so the cloud mirrors that shape:
one remote Turso database per year, named by an environment variable keyed on
the year.

    TURSO_AUTH_TOKEN=<token from `turso db tokens create`>
    TURSO_URL_2023=https://<db>-<org>.turso.io
    TURSO_URL_2024=...
    TURSO_URL_2025=...
    TURSO_URL_2026=...

Values are read from a `.env` file at the project root (git-ignored) and then
from the real environment, so exporting a variable in your shell always wins
over the file. A year with no URL is simply not a cloud year: it is skipped by
the caller rather than treated as an error, which is what keeps the headless
scripts (seed/smoke tests) running purely embedded.

Note that Jouduto reaches Turso through the SDK's *sync* driver
(`turso.sync.connect`): reads are served from a local embedded replica and
replicate with the remote. There is no HTTP-only remote driver in pyturso.
"""

from __future__ import annotations

import os

AUTH_TOKEN_VAR = "TURSO_AUTH_TOKEN"
REMOTE_URL_PREFIX = "TURSO_URL_"

# How long a replica is allowed to wait on a `pull()` before giving up and
# serving whatever is already on disk. Keeps a slow/absent network from
# freezing the UI on startup.
DEFAULT_PULL_TIMEOUT_MS = 1_000

_CLIENT_NAME = "jouduto"


class TursoConfigError(RuntimeError):
    """Raised when Turso settings are missing or unusable."""


def project_root() -> str:
    """Walk up from this file looking for pyproject.toml, else fall back to CWD.

    Resolving the root this way keeps `.env` discovery independent of where the
    app happens to be launched from (the legacy `DATA_DIR = "data"` is still
    CWD-relative, which is a separate wart we leave alone).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    current = here
    while True:
        if os.path.isfile(os.path.join(current, "pyproject.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.getcwd()
        current = parent


def _env_file_path() -> str:
    return os.path.join(project_root(), ".env")


def _parse_env_file(path: str) -> None:
    """Minimal KEY=VALUE loader used when python-dotenv is not installed.

    Only fills variables that are not already set, matching dotenv's default
    "real environment wins" behaviour.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ.setdefault(key, value)


def load() -> str:
    """Load `.env` into the environment (once) and return its path."""
    path = _env_file_path()
    try:
        from dotenv import load_dotenv
    except ImportError:
        _parse_env_file(path)
    else:
        load_dotenv(path, override=False)
    return path


def env_file_path() -> str:
    """The `.env` path this module reads (does not load it)."""
    return _env_file_path()


def get_remote_url(year: int) -> str | None:
    """Remote URL for `year`, or None when that year has no cloud database."""
    load()
    url = os.environ.get(f"{REMOTE_URL_PREFIX}{year}", "").strip()
    if not url:
        return None
    return url


def get_auth_token() -> str:
    """The Turso auth token. Raises a pointed error when it is missing."""
    load()
    token = os.environ.get(AUTH_TOKEN_VAR, "").strip()
    if not token:
        raise TursoConfigError(
            f"{AUTH_TOKEN_VAR} is not set. Add it to {_env_file_path()} "
            f"(see .env.example) or export it before starting the app."
        )
    return token


def pull_timeout_ms() -> int:
    """How long a replica may wait on `pull()` before serving local data."""
    load()
    raw = os.environ.get("TURSO_PULL_TIMEOUT_MS", "").strip()
    if not raw:
        return DEFAULT_PULL_TIMEOUT_MS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_PULL_TIMEOUT_MS


def client_name() -> str:
    return _CLIENT_NAME


def configured_years(years) -> list[int]:
    """The subset of `years` that has a remote URL configured."""
    return [year for year in years if get_remote_url(year) is not None]


def is_cloud_enabled() -> bool:
    """True when at least one fiscal year is wired up to Turso."""
    return bool(configured_years(range(1990, 2100)))
