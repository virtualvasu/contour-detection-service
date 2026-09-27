"""Unit checks for turning grid-cell masks into boundary polygons."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.catchment import mask_to_polygon


class _Identity:
    """Stand-in for a pyproj transformer that leaves coordinates as they are."""

    def transform(self, xs, ys):
        return xs, ys


def _fake_dem(rows: int, cols: int, cell_size: float):
    return SimpleNamespace(
        cell_size=cell_size,
        x_coords=500_000.0 + (np.arange(cols) + 0.5) * cell_size,
        y_coords=2_350_000.0 - (np.arange(rows) + 0.5) * cell_size,
        transformer_to_lonlat=_Identity(),
    )


# Awkward cell sizes like these (as produced when a selected area sets the
# grid) used to leave floating-point gaps between rows.
@pytest.mark.parametrize("cell_size", [3.6995972340754184, 6.289828223893342, 10.0])
def test_solid_block_becomes_one_ring(cell_size):
    dem = _fake_dem(40, 40, cell_size)
    mask = np.zeros((40, 40), dtype=bool)
    mask[5:25, 8:30] = True

    rings = mask_to_polygon(mask, dem)

    assert len(rings) == 1
    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    assert max(xs) - min(xs) == pytest.approx(22 * cell_size)
    assert max(ys) - min(ys) == pytest.approx(20 * cell_size)


def test_empty_mask_has_no_rings():
    assert mask_to_polygon(np.zeros((5, 5), dtype=bool), _fake_dem(5, 5, 1.0)) == []
