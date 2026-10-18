import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from codegate.services.github_app import GitHubAppService


def test_app_jwt_uses_verifiable_rs256_and_short_expiration(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    service = GitHubAppService()
    service.app_id = "12345"
    monkeypatch.setattr(service, "_get_private_key", lambda: private_pem)

    token = service._generate_jwt()

    claims = jwt.decode(token, private_key.public_key(), algorithms=["RS256"], issuer="12345")
    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    assert claims["iat"] <= int(time.time())
    assert 0 < claims["exp"] - int(time.time()) <= 8 * 60
    with pytest.raises(jwt.InvalidSignatureError):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwt.decode(token, other_key.public_key(), algorithms=["RS256"], issuer="12345")
