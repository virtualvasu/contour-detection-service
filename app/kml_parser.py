"""Parse contour lines out of a KML or KMZ file.

The only assumption made about the input is the one that defines a
"contour map": it is a KML document containing Placemarks, each of
which is a line (or polygon outline) of constant elevation, and each
of which carries that elevation as a number somewhere in its <name>.
No coordinates, region, or file-specific structure is assumed, so the
same parser works for any contour map exported in this style, not just
the sample file.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from lxml import etree

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class ContourLine:
    elevation: float
    # list of (lon, lat) vertices, in the order they appear in the KML
    points: list[tuple[float, float]]


def _local(tag: str) -> str:
    """Strip an XML namespace off a tag, e.g. '{ns}Placemark' -> 'Placemark'."""
    return tag.rsplit("}", 1)[-1]


def _find_all(elem, name: str):
    return [e for e in elem.iter() if _local(e.tag) == name]


def _first_text(elem, name: str) -> str | None:
    for e in elem.iter():
        if _local(e.tag) == name:
            return e.text
    return None


def _extract_elevation(name_text: str | None) -> float | None:
    if not name_text:
        return None
    match = _NUMBER_RE.search(name_text.strip())
    if not match:
        return None
    return float(match.group())


def _parse_coordinates(text: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if not text:
        return points
    for tuple_str in text.split():
        parts = tuple_str.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        points.append((lon, lat))
    return points


def _load_kml_bytes(raw: bytes) -> bytes:
    """Return raw KML bytes, unzipping the first .kml entry if this is a KMZ."""
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise ValueError("KMZ archive does not contain a .kml file")
                # Prefer doc.kml if present, matching common KMZ conventions.
                kml_names.sort(key=lambda n: (n.lower() != "doc.kml", n))
                return zf.read(kml_names[0])
        except zipfile.BadZipFile as exc:
            raise ValueError("Uploaded file looks like a KMZ but is not a valid zip archive") from exc
    return raw


def parse_contours(raw: bytes) -> list[ContourLine]:
    """Extract every elevation-labelled line/polygon Placemark from a KML/KMZ file."""
    kml_bytes = _load_kml_bytes(raw)
    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        root = etree.fromstring(kml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Could not parse the file as XML/KML: {exc}") from exc
    if root is None:
        raise ValueError("Uploaded file does not contain valid KML content")

    contours: list[ContourLine] = []
    for placemark in _find_all(root, "Placemark"):
        elevation = _extract_elevation(_first_text(placemark, "name"))
        if elevation is None:
            continue

        coord_texts = [_first_text(g, "coordinates") for g in
                       (_find_all(placemark, "LineString") +
                        _find_all(placemark, "LinearRing"))]
        coord_texts = [c for c in coord_texts if c]
        if not coord_texts:
            continue

        for coord_text in coord_texts:
            points = _parse_coordinates(coord_text)
            if len(points) >= 2:
                contours.append(ContourLine(elevation=elevation, points=points))

    if not contours:
        raise ValueError(
            "No elevation-labelled contour lines found in the uploaded file"
        )
    return contours
