from __future__ import annotations

from app.analysis.reconstruction.backends import GraphdecoBackend, GsplatBackend


class ReconstructionBackendRegistry:
    def __init__(self) -> None:
        self._backends = {
            "gsplat_3dgs": GsplatBackend(),
            "graphdeco_3dgs": GraphdecoBackend(),
        }

    def get(self, name: str):
        try:
            return self._backends[name]
        except KeyError as error:
            raise ValueError(f"不支援的三維模型後端：{name}") from error

    def check(self, name: str) -> dict:
        return self.get(name).check_availability()

    def probe_runtime(self, name: str) -> dict:
        backend = self.get(name)
        probe = getattr(backend, "probe_runtime", None)
        return probe() if callable(probe) else backend.check_availability()

    def list_readiness(self) -> list[dict]:
        return [backend.check_availability() for backend in self._backends.values()]
