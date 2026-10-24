"""轮询协调器（可选）。

实体本身走 local_push，这个协调器只在需要定时主动查询时使用。
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class Air352UpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, hub, interval: int = 60):
        self.hub = hub
        super().__init__(
            hass,
            _LOGGER,
            name=f"352_{hub.mac}",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self):
        await self.hub.async_query()
        return self.hub.status
