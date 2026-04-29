from abc import ABC, abstractmethod


class GridBackend(ABC):
    @abstractmethod
    def point_to_cell(self, lat: float, lon: float, level: int) -> str:
        """Map a lat/lon coordinate to a cell ID at the given level."""
        ...

    @abstractmethod
    def cell_to_centroid(self, cell_id: str) -> tuple[float, float]:
        """Return the (lat, lon) centroid of a cell."""
        ...

    @abstractmethod
    def cell_parent(self, cell_id: str) -> str:
        """Return the parent cell ID one level coarser."""
        ...

    @abstractmethod
    def cell_children(self, cell_id: str) -> list[str]:
        """Return child cell IDs one level finer."""
        ...

    @abstractmethod
    def level_to_approx_resolution_km(self, level: int) -> float:
        """Return the approximate cell edge length in km for a given level."""
        ...

    @abstractmethod
    def cell_level(self, cell_id: str) -> int:
        """Return the level encoded in a cell_id."""
        ...
