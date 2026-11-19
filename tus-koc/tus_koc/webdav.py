"""Kullanıcının Markdown klasörünü WebDAV ile açar (Obsidian + Remotely Save için).

Her kullanıcı yalnız kendi klasörünü görür: kimlik doğrulayıcı kullanıcıyı bulur,
dosya sağlayıcısı kök klasörü o kullanıcının klasörüne kilitler.
Şifre hesap şifresi değil, /hesap/obsidian sayfasında üretilen uygulama şifresidir.
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

_ANAHTAR = "tus_koc.user_id"
# Kasanın yönetilen çalışma dosyaları iPad'e eşitlenmez ve oradan değiştirilemez; aksi halde
# avenoxbeyin güncellemesi "managed file changed" çakışmasıyla durur. Notlar, Companion,
# görevler ve Ekler eşitlenir.
GIZLI_KOK = {"beyin.py", "AGENTS.md", "CLAUDE.md"}


def _gizli(parts: list[str]) -> bool:
    return any(p.startswith(".") for p in parts) or (len(parts) == 1 and parts[0] in GIZLI_KOK)


class _Klasor(FolderResource):
    def get_member_names(self):
        kok = self.path.strip("/") == ""
        return [n for n in super().get_member_names() if not n.startswith(".") and not (kok and n in GIZLI_KOK)]


class KullaniciKlasoru(FilesystemProvider):
    def _loc_to_file_path(self, path: str, environ: dict | None = None):
        user_id = (environ or {}).get(_ANAHTAR)
        if not user_id:
            raise DAVError(HTTP_FORBIDDEN)
        root = Path(self.root_folder_path) / user_id
        root.mkdir(parents=True, exist_ok=True)
        root_real = os.path.realpath(root)
        parts = [p for p in path.strip("/").split("/") if p]
        if _gizli(parts):
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
        return _Klasor(path, environ, fp) if os.path.isdir(fp) else FileResource(path, environ, fp)


class HesapDogrulayici(BaseDomainController):
    def __init__(self, wsgidav_app, config):
        super().__init__(wsgidav_app, config)
        self.db: DB = config["tus_koc_db"]

    def get_domain_realm(self, path_info, environ):
        return "TUS Koc"  # ASCII: wsgidav 401 gövdesinin uzunluğunu karakterle hesaplıyor

    def require_authentication(self, realm, environ):
        return True

    def basic_auth_user(self, realm, user_name, password, environ):
        user_id = self.db.dav_giris(user_name, password)
        if not user_id:
            return False
        environ[_ANAHTAR] = user_id
        return True

    def supports_http_digest_auth(self):
        return False


def webdav_uygulamasi(db: DB, vault_root: Path):
    vault_root.mkdir(parents=True, exist_ok=True)
    config = {
        "provider_mapping": {"/": KullaniciKlasoru(str(vault_root))},
        "http_authenticator": {
            "domain_controller": HesapDogrulayici,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        # Dizin tarayıcısı ve CORS yok: istemci Obsidian eklentisi, tarayıcı değil.
        "middleware_stack": [ErrorPrinter, HTTPAuthenticator, RequestResolver],
        "tus_koc_db": db,
        "verbose": 1,
        "logging": {"enable": False},
        "lock_storage": True,
        "property_manager": True,
        "hotfixes": {"re_encode_path_info": True},
    }
    return _YolKorumasi(WSGIMiddleware(WsgiDAVApp(config)))


class _YolKorumasi:
    """`..` içeren yolları WebDAV'a hiç ulaştırmadan reddeder.

    wsgidav bu yolları zaten reddediyor ama boş gövdeyle yanlış Content-Length gönderiyor.
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
