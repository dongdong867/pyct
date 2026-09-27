"""A sweep fixture: a settings object that raises when anything asks its class, as a lazy
settings proxy does before it is configured."""


class _Lazy:
    @property
    def __class__(self):
        raise RuntimeError("settings are not configured")


settings = _Lazy()
