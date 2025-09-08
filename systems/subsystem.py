import threading, time, traceback


class Subsystem(threading.Thread):
    def __init__(self, state, name=None):
        super().__init__(daemon=True)
        self.name = name or self.__class__.__name__.lower()
        self.state = state  # SharedState instance
        self._stop_event = threading.Event()
        self._ready = False

    def init_hardware(self):
        """Override this to init hardware."""
        pass

    def loop(self):
        """Override this. Called repeatedly until shutdown."""
        pass

    def publish(self, **kv):
        """Update your subsystem’s status in the shared state."""
        self.state.put(self.name, **kv)

    def run(self):
        try:
            self.publish(status='initializing')
            self.init_hardware()
            self._ready = True
            self.publish(status='ok')
        except Exception as e:
            self.publish(status='error', error=str(e))
            traceback.print_exc()
            return

        while not self._stop_event.is_set():
            try:
                self.loop()
            except Exception as e:
                self.publish(status='error', error=str(e))
                traceback.print_exc()
                break

        self.publish(status='off')

    def shutdown(self):
        self._stop_event.set()

    @property
    def is_running(self):
        return self.is_alive() and self._ready
