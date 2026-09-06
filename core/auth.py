"""
Authentication and PIN Security Manager for Linux Continuity.
Protects remote connections with a 4-digit security PIN and session tokens.
Developed by killindodo
"""

import os
import json
import secrets
import uuid
from typing import Optional


class AuthManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/linux-continuity")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.pin: str = "7492"
        self.require_pin: bool = True
        self.valid_tokens = set()

        os.makedirs(self.config_dir, exist_ok=True)
        self._load_config()

        # Generate a master token for QR code auto-login
        self.master_token = uuid.uuid4().hex
        self.valid_tokens.add(self.master_token)

    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.pin = str(data.get("pin", self._generate_pin()))
                    self.require_pin = bool(data.get("require_pin", True))
            except Exception:
                self.pin = self._generate_pin()
                self._save_config()
        else:
            self.pin = self._generate_pin()
            self._save_config()

    def _save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump({
                    "pin": self.pin,
                    "require_pin": self.require_pin
                }, f, indent=2)
        except Exception:
            pass

    def _generate_pin(self) -> str:
        return f"{secrets.randbelow(9000) + 1000}"

    def set_pin(self, new_pin: str):
        if len(new_pin) >= 4:
            self.pin = str(new_pin)
            self._save_config()

    def set_require_pin(self, required: bool):
        self.require_pin = required
        self._save_config()

    def verify_pin(self, pin_attempt: str) -> Optional[str]:
        if not self.require_pin or str(pin_attempt).strip() == self.pin:
            token = uuid.uuid4().hex
            self.valid_tokens.add(token)
            return token
        return None

    def is_authorized(self, token: Optional[str]) -> bool:
        if not self.require_pin:
            return True
        return token in self.valid_tokens
