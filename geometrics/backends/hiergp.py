import pandas as pd
from hiergp import hierGP
from geometrics.backends.base import GridBackend

_BASE_SIZE_M = 25
_MAX_LEVELS = 15

# Resolution in km at each internal HierGP level (1=finest, 15=coarsest)
# (base_size_m / 1000) * 2^(internal_level - 1)
_INTERNAL_LEVEL_KM = {
    lvl: (_BASE_SIZE_M / 1000) * (2 ** (lvl - 1))
    for lvl in range(1, _MAX_LEVELS + 1)
}


def _to_internal(level: int) -> int:
    """Convert standardised level (15=finest) to HierGP internal level (1=finest)."""
    return _MAX_LEVELS + 1 - level


def _to_standard(internal: int) -> int:
    """Convert HierGP internal level (1=finest) to standardised level (15=finest)."""
    return _MAX_LEVELS + 1 - internal


class HierGPBackend(GridBackend):
    """
    Rectangular grid backend wrapping the HierGP library.

    Fixed configuration: base_size=25m, 15 levels.

    Standardised level convention (matches H3): higher level = finer resolution.
      Standard level 15 = 25 m (finest)
      Standard level 1  = 409.6 km (coarsest)

    cell_id format: "{standard_level}:{x}|{y}"
    """

    def __init__(self):
        self._grider = hierGP(base_size=_BASE_SIZE_M)

    def point_to_cell(self, lat: float, lon: float, level: int) -> str:
        internal = _to_internal(level)
        df = pd.DataFrame({'latitude': [lat], 'longitude': [lon]})
        grids = self._grider.generateGrids(df, internal)
        x = int(grids[f'l{internal}_x'].iloc[0])
        y = int(grids[f'l{internal}_y'].iloc[0])
        return f"{level}:{x}|{y}"

    def cell_to_centroid(self, cell_id: str) -> tuple[float, float]:
        level, xy = cell_id.split(':')
        x, y = xy.split('|')
        internal = _to_internal(int(level))
        cell_df = pd.DataFrame({'x': [int(x)], 'y': [int(y)]})
        result = self._grider.generateCenters(cell_df, internal)
        return (result[f'l{internal}_lat'].iloc[0], result[f'l{internal}_lon'].iloc[0])

    def cell_parent(self, cell_id: str) -> str:
        x, y, level = self._grider.decode_cell_id(cell_id)
        internal = _to_internal(level)
        px, py, parent_internal = self._grider.cell_parent(x, y, internal)
        return self._grider.encode_cell_id(px, py, _to_standard(parent_internal))

    def cell_children(self, cell_id: str) -> list[str]:
        x, y, level = self._grider.decode_cell_id(cell_id)
        internal = _to_internal(level)
        child_tuples = self._grider.cell_children(x, y, internal)
        child_standard = _to_standard(child_tuples[0][2])
        return [self._grider.encode_cell_id(cx, cy, child_standard) for cx, cy, _ in child_tuples]

    def level_to_approx_resolution_km(self, level: int) -> float:
        return _INTERNAL_LEVEL_KM[_to_internal(level)]

    def cell_level(self, cell_id: str) -> int:
        _, _, level = self._grider.decode_cell_id(cell_id)
        return level
