"""
Set a maximum on time for certain items.
"""
import asyncio
from typing import Any
from collections.abc import Coroutine
import appdaemon.plugins.hass.hassapi as hass

DEFAULT_TIMEOUT = 2700

class Allowance(hass.Hass):
    """Main class."""
    async def initialize(self):
        """Initialize the class."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.timeout = self.args.get("timeout", DEFAULT_TIMEOUT)
        # define light entities switched by automotionlight
        self.gv_entities: set[str] = self.args.pop("entities", set())

        listener: set[Coroutine[Any, Any, Any]] = set()
        for entity in self.gv_entities:
            listener.add(
                self.listen_state(self.timeout_reached,
                entity_id=entity,
                new="on",
                duration=self.timeout)
            )

        await asyncio.gather(*listener)

    async def timeout_reached(
        self, entity: str, attribute: str, old: str, new: str, _: dict[str, Any]
    ) -> None:
        """Turn off the entity if it has been on too long."""
        await self.turn_off(entity_id=entity)
