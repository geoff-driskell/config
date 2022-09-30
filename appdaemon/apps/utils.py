import appdaemon.plugins.hass.hassapi as hass


class AutoMotionLights(hass.Hass):
    def ha_logger(
        self,
        message: str,
        *args: Any,
        level: int,
        icon: str,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("ascii_encode", False)
        level = level

        message = f"{icon}{message}"
        