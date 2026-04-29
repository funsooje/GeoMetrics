import h3
from geometrics.backends.base import GridBackend

# Approximate edge lengths in km for H3 resolutions 0–15
# Source: https://h3geo.org/docs/core-library/restable/
_H3_EDGE_LENGTH_KM = {
    0: 1107.71, 1: 418.68, 2: 158.24, 3: 59.81,
    4: 22.61,  5: 8.54,   6: 3.23,   7: 1.22,
    8: 0.461,  9: 0.174, 10: 0.066, 11: 0.025,
    12: 0.009, 13: 0.003, 14: 0.001,
}


class H3Backend(GridBackend):
    """
    Hexagonal grid backend wrapping the H3 library (Uber).

    level maps directly to H3 resolution (0 = coarsest, 14 = finest).
    cell_id is the native H3 index string.
    """

    def point_to_cell(self, lat: float, lon: float, level: int) -> str:
        return h3.latlng_to_cell(lat, lon, level)

    def cell_to_centroid(self, cell_id: str) -> tuple[float, float]:
        lat, lon = h3.cell_to_latlng(cell_id)
        return (lat, lon)

    def cell_parent(self, cell_id: str) -> str:
        res = h3.get_resolution(cell_id)
        return h3.cell_to_parent(cell_id, res - 1)

    def cell_children(self, cell_id: str) -> list[str]:
        res = h3.get_resolution(cell_id)
        return list(h3.cell_to_children(cell_id, res + 1))

    def level_to_approx_resolution_km(self, level: int) -> float:
        return _H3_EDGE_LENGTH_KM[level]

    def cell_level(self, cell_id: str) -> int:
        return h3.get_resolution(cell_id)
