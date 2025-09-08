import threading, time, copy, json


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def put(self, who: str, **kv):
        def _coerce(v):
            if isinstance(v, (int, float)):
                return float(v)
            elif isinstance(v, (list, dict)):
                return v
            else:
                return str(v)

        safe = {k: _coerce(v) for k, v in kv.items()}
        safe["ts"] = time.time()
        with self._lock:
            self._data[who] = safe

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def json(self):
        return json.dumps(self.snapshot(), default=str)
