"""352 空气净化器配置流程。"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, MODELS

_LOGGER = logging.getLogger(__name__)


def _parse_auth(value) -> int | None:
    """接受 '0x22B5'、'22B5'、'8885' 这几种写法。"""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    try:
        return int(text, 16)
    except ValueError:
        return None


class Air352ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            auth_raw = user_input.get("auth", "")
            auth = _parse_auth(auth_raw)
            if auth_raw not in (None, "") and auth is None:
                errors["auth"] = "invalid_auth"
            else:
                mac = user_input["mac"].replace(":", "").replace("-", "").upper()
                if len(mac) != 12:
                    errors["mac"] = "invalid_mac"
                else:
                    data = {
                        "model": user_input["model"],
                        "host": user_input["host"].strip(),
                        "mac": mac,
                    }
                    if auth is not None:
                        data["auth"] = auth
                    return self.async_create_entry(
                        title=f"{MODELS[user_input['model']]['name']} ({user_input['host']})",
                        data=data,
                    )

        schema = vol.Schema(
            {
                vol.Required("model", default="x50s"): vol.In(
                    {key: info["name"] for key, info in MODELS.items()}
                ),
                vol.Required("host", default="192.168.1.100"): str,
                vol.Required("mac", default="00:95:69:00:00:00"): str,
                vol.Optional("auth", default=""): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
