"""Завдання №45: OAuth2 / OpenID Connect «Увійти через …»: authorization code + PKCE.

Реалізуй клієнтську частину (relying party). Мережі тут немає: обмін коду на токени
виконує функція `token_exchange`, яку передають у конструктор (у production це POST на
token endpoint провайдера), а `session` це словник серверної сесії користувача.

code_challenge(verifier) -> str
    PKCE S256 (RFC 7636): BASE64URL-без-`=`(SHA256(verifier ASCII)).
new_verifier(token_bytes) -> str
    `token_bytes(n) -> bytes` (у production `secrets.token_bytes`). Verifier це base64url без `=`
    від 32 випадкових байтів (43 символи).

OAuthClient(client_id, redirect_uri, authorize_url, issuer, token_exchange, token_bytes, clock, scopes=("openid", "email"))
  .start(session) -> str  URL, куди перенаправити користувача:
        параметри: response_type=code, client_id, redirect_uri, scope (через пробіл), state, nonce,
        code_challenge, code_challenge_method=S256. `state` і `nonce` це окремі випадкові рядки
        (base64url від 16 байтів), verifier ще один. У `session["oauth"]` зберігається
        {"state", "nonce", "verifier", "created_at"}; verifier і nonce в URL НЕ потрапляють у відкритому вигляді
        (nonce так, але verifier ніколи).
  .callback(session, params) -> Login  обробка повернення на redirect_uri (`params` це query-параметри):
        1. `session["oauth"]` ВИДАЛЯЄТЬСЯ одразу (одноразове): його немає -> OAuthError;
        2. `error` у params -> OAuthError (обмін не виконується);
        3. state має збігатися зі збереженим (порівняння сталого часу); немає/інший -> OAuthError, обмін не виконується;
        4. з моменту `start` пройшло понад 600 секунд -> OAuthError;
        5. немає `code` -> OAuthError;
        6. `token_exchange(code=..., code_verifier=..., redirect_uri=..., client_id=...)` -> dict відповіді
           провайдера; будь-який виняток з нього перетворюється на OAuthError;
        7. перевірка відповіді: `token_type` (без урахування регістру) це "bearer", `access_token` непорожній,
           є `id_token`; в id_token (`decode_jwt_payload`): `iss` == issuer, `aud` == client_id (рядок або список,
           що його містить), `exp` у майбутньому, `nonce` == збережений; інакше OAuthError;
        8. Login(subject=sub, email=email або None, access_token, expires_at=clock() + expires_in).
"""
import base64
import hashlib  # noqa: F401
import hmac  # noqa: F401
import json
from dataclasses import dataclass
from typing import Any, Callable


class OAuthError(Exception):
    pass


@dataclass
class Login:
    subject: str
    email: str | None
    access_token: str
    expires_at: float


def decode_jwt_payload(token: str) -> dict:
    """Лише розбирає payload JWT (без перевірки підпису). Підпис id_token у production
    перевіряють за ключами провайдера (JWKS), див. завдання №51; тут довіряємо каналу TLS."""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception as exc:
        raise OAuthError("malformed id_token") from exc


def code_challenge(verifier: str) -> str:
    raise NotImplementedError


def new_verifier(token_bytes: Callable[[int], bytes]) -> str:
    raise NotImplementedError


class OAuthClient:
    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        authorize_url: str,
        issuer: str,
        token_exchange: Callable[..., dict[str, Any]],
        token_bytes: Callable[[int], bytes],
        clock: Callable[[], float],
        scopes: tuple[str, ...] = ("openid", "email"),
    ) -> None:
        raise NotImplementedError

    def start(self, session: dict) -> str:
        raise NotImplementedError

    def callback(self, session: dict, params: dict[str, str]) -> Login:
        raise NotImplementedError
