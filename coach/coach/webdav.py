"""Serves the user's Markdown folder over WebDAV (for Obsidian + Remotely Save).

Each user only sees their own folder: the authenticator finds the user and the file provider locks
the root folder to that user's folder. The password is not the account password but the app password
created on the /account/obsidian page.
"""
from __future__ import annotations

import os
from pathlib import Path

from a2wsgi import WSGIMiddleware
from wsgidav.dav_error import HTTP_FORBIDDEN, HTTP_NOT_FOUND, DAVError
from wsgidav.dc.base_dc import BaseDomainController
from wsgidav.error_printer import ErrorPrinter
from wsgidav.http_authenticator import HTTPAuthenticator
from wsgidav.request_resolver import RequestResolver
from wsgidav.fs_dav_provider import FileResource, FilesystemProvider, FolderResource
from wsgidav.wsgidav_app import WsgiDAVApp

from .db import DB

_KEY = "coach.user_id"
# The vault's managed engine files are not synced to the iPad and can't be changed from there; otherwise an
# avenoxbeyin update stops with a "managed file changed" conflict. Notes, Companion, tasks and attachments sync.
HIDDEN_ROOT = {"beyin.py", "AGENTS.md", "CLAUDE.md"}


def _hidden(parts: list[str]) -> bool:
    return any(p.startswith(".") for p in parts) or (len(parts) == 1 and parts[0] in HIDDEN_ROOT)


class _Folder(FolderResource):
    def get_member_names(self):
        root = self.path.strip("/") == ""
        return [n for n in super().get_member_names() if not n.startswith(".") and not (root and n in HIDDEN_ROOT)]


class UserFolder(FilesystemProvider):
    def _loc_to_file_path(self, path: str, environ: dict | None = None):
        user_id = (environ or {}).get(_KEY)
        if not user_id:
            raise DAVError(HTTP_FORBIDDEN)
        root = Path(self.root_folder_path) / user_id
        root.mkdir(parents=True, exist_ok=True)
        root_real = os.path.realpath(root)
        parts = [p for p in path.strip("/").split("/") if p]
        if _hidden(parts):
            raise DAVError(HTTP_NOT_FOUND)
        file_path = os.path.abspath(os.path.join(root, *parts))
        real = os.path.realpath(file_path)
        if real != root_real and not real.startswith(root_real + os.sep):
            raise DAVError(HTTP_FORBIDDEN)
        return file_path


    def get_resource_inst(self, path: str, environ: dict):
        fp = self._loc_to_file_path(path, environ)
        if not os.path.exists(fp) or os.path.islink(fp):
            return None
        return _Folder(path, environ, fp) if os.path.isdir(fp) else FileResource(path, environ, fp)


class AccountAuthenticator(BaseDomainController):
    def __init__(self, wsgidav_app, config):
        super().__init__(wsgidav_app, config)
        self.db: DB = config["coach_db"]

    def get_domain_realm(self, path_info, environ):
        return "Study Coach"  # ASCII: wsgidav computes the 401 body length in characters

    def require_authentication(self, realm, environ):
        return True

    def basic_auth_user(self, realm, user_name, password, environ):
        user_id = self.db.dav_login(user_name, password)
        if not user_id:
            return False
        environ[_KEY] = user_id
        return True

    def supports_http_digest_auth(self):
        return False


def webdav_app(db: DB, vault_root: Path):
    vault_root.mkdir(parents=True, exist_ok=True)
    config = {
        "provider_mapping": {"/": UserFolder(str(vault_root))},
        "http_authenticator": {
            "domain_controller": AccountAuthenticator,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        # No directory browser and no CORS: the client is the Obsidian plugin, not a browser.
        "middleware_stack": [ErrorPrinter, HTTPAuthenticator, RequestResolver],
        "coach_db": db,
        "verbose": 1,
        "logging": {"enable": False},
        "lock_storage": True,
        "property_manager": True,
        "hotfixes": {"re_encode_path_info": True},
    }
    return _PathGuard(WSGIMiddleware(WsgiDAVApp(config)))


class _PathGuard:
    """Rejects paths containing `..` before they reach WebDAV.

    wsgidav rejects them too, but sends a wrong Content-Length with an empty body.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and ".." in scope.get("path", "").split("/"):
            await send({"type": "http.response.start", "status": 400,
                        "headers": [(b"content-type", b"text/plain"), (b"content-length", b"11")]})
            await send({"type": "http.response.body", "body": b"Bad Request"})
            return
        await self.app(scope, receive, send)
