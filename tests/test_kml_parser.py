"""Parser checks for KMZ input."""

import io
import pathlib
import zipfile

import pytest

from app import kml_parser
from app.kml_parser import parse_contours

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "contours_1m.kml"


@pytest.fixture(scope="module")
def sample_kmz() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", SAMPLE_PATH.read_bytes())
    return buf.getvalue()


def test_kmz_parses_like_kml(sample_kmz):
    assert len(parse_contours(sample_kmz)) == len(parse_contours(SAMPLE_PATH.read_bytes()))


def test_kmz_with_oversized_kml_is_rejected(sample_kmz, monkeypatch):
    monkeypatch.setattr(kml_parser, "MAX_UNZIPPED_KML_BYTES", 1000)
    with pytest.raises(ValueError, match="too large"):
        parse_contours(sample_kmz)
