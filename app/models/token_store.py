"""Storage and lifecycle management for permanent consumer API tokens."""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from app.core.config import settings
from app.core.security import generate_consumer_token, hash_token, timing_safe_compare
from app.models.schemas import TokenInfo

logger = logging.getLogger(__name__)


class TokenStore:
    """Manages persistent tokens for API consumers in a thread-safe, secure manner."""
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or settings.TOKEN_STORAGE_PATH
        self._lock = asyncio.Lock()
        self._tokens: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        """Loads tokens from persistent file if it exists."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tokens = {item["id"]: item for item in data.get("tokens", [])}
            except Exception as e:
                logger.error(f"Error cargando archivo de tokens {self.file_path}: {e}")
                self._tokens = {}
        else:
            self._tokens = {}

    def _save(self) -> None:
        """Persists tokens safely to disk."""
        try:
            temp_path = f"{self.file_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump({"tokens": list(self._tokens.values())}, f, indent=2)
            os.replace(temp_path, self.file_path)
        except Exception as e:
            logger.error(f"Error guardando tokens en {self.file_path}: {e}")

    async def create_token(self, nombre: str) -> Tuple[str, TokenInfo]:
        """
        Creates a new permanent cryptographic token for a consumer.
        Returns the plaintext token (ONLY ONCE) and its public metadata.
        """
        raw_token = generate_consumer_token()
        hashed = hash_token(raw_token)
        token_id = str(uuid.uuid4())
        prefix = raw_token[:13] + "..."  # e.g. "tok_live_1234..."
        now = datetime.now(timezone.utc).isoformat()

        token_record = {
            "id": token_id,
            "nombre": nombre,
            "token_hash": hashed,
            "prefijo": prefix,
            "activo": True,
            "created_at": now,
            "last_used_at": None,
            "revoked_at": None
        }

        async with self._lock:
            self._tokens[token_id] = token_record
            self._save()

        info = TokenInfo(
            id=token_id,
            nombre=nombre,
            prefijo=prefix,
            activo=True,
            created_at=now,
            last_used_at=None,
            revoked_at=None
        )
        return raw_token, info

    async def verify_token(self, raw_token: str) -> Optional[TokenInfo]:
        """
        Verifies a bearer token against active stored tokens and env var API_TOKEN.
        Updates last_used_at on success.
        """
        if not raw_token:
            return None

        # 1. Check against static API_TOKEN env var if configured
        if settings.API_TOKEN and timing_safe_compare(raw_token, settings.API_TOKEN):
            return TokenInfo(
                id="env-default-token",
                nombre="Default Environment Consumer",
                prefijo=settings.API_TOKEN[:8] + "...",
                activo=True,
                created_at="2026-01-01T00:00:00Z",
                last_used_at=datetime.now(timezone.utc).isoformat(),
                revoked_at=None
            )

        # 2. Check hashed database tokens
        incoming_hash = hash_token(raw_token)
        async with self._lock:
            for item in self._tokens.values():
                if item.get("activo") and timing_safe_compare(item.get("token_hash", ""), incoming_hash):
                    # Update last_used_at
                    now = datetime.now(timezone.utc).isoformat()
                    item["last_used_at"] = now
                    self._save()
                    return TokenInfo(
                        id=item["id"],
                        nombre=item["nombre"],
                        prefijo=item["prefijo"],
                        activo=item["activo"],
                        created_at=item["created_at"],
                        last_used_at=item["last_used_at"],
                        revoked_at=item["revoked_at"]
                    )

        return None

    async def revoke_token(self, token_id: str) -> bool:
        """Revokes an existing token by ID."""
        async with self._lock:
            if token_id in self._tokens:
                self._tokens[token_id]["activo"] = False
                self._tokens[token_id]["revoked_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    async def list_tokens(self) -> List[TokenInfo]:
        """Lists metadata of all registered consumer tokens."""
        async with self._lock:
            result = []
            for item in self._tokens.values():
                result.append(
                    TokenInfo(
                        id=item["id"],
                        nombre=item["nombre"],
                        prefijo=item["prefijo"],
                        activo=item["activo"],
                        created_at=item["created_at"],
                        last_used_at=item.get("last_used_at"),
                        revoked_at=item.get("revoked_at")
                    )
                )
            return sorted(result, key=lambda x: x.created_at, reverse=True)


# Global singleton instance
token_store = TokenStore()
