class Serial:
    """Minimal stub emulating pyserial's Serial class."""
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def write(self, data):
        return len(data)

    def flush(self):
        pass
