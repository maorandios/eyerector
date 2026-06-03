"""Placeholder frame detection for vision PDF extraction."""

from analyzer_service.pdf_validate.schematic import detect_schematic_placeholder
from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec


def _col(el_id: str, x: float, y: float, h: float) -> PureSteelElementSpec:
    return PureSteelElementSpec(
        id=el_id,
        profile_name="HEB300",
        start_x=x,
        start_y=y,
        start_z=0,
        end_x=x,
        end_y=y,
        end_z=h,
    )


def _beam(el_id: str, x1: float, y1: float, x2: float, y2: float, z: float) -> PureSteelElementSpec:
    return PureSteelElementSpec(
        id=el_id,
        profile_name="IPE200",
        start_x=x1,
        start_y=y1,
        start_z=z,
        end_x=x2,
        end_y=y2,
        end_z=z,
    )


def test_detects_four_column_placeholder() -> None:
    h = 6000.0
    lx, ly = 12000.0, 12000.0
    model = PureStructuralModelSpec(
        elements=[
            _col("c1", 0, 0, h),
            _col("c2", lx, 0, h),
            _col("c3", lx, ly, h),
            _col("c4", 0, ly, h),
            _beam("t1", 0, 0, lx, 0, h),
            _beam("t2", lx, 0, lx, ly, h),
            _beam("t3", lx, ly, 0, ly, h),
            _beam("t4", 0, ly, 0, 0, h),
            _beam("m1", 0, 0, lx, 0, h / 2),
            _beam("m2", lx, 0, lx, ly, h / 2),
            _beam("m3", 0, ly, lx, ly, h / 2),
        ],
        slabs=[],
    )
    check = detect_schematic_placeholder(model, dense_cad=True)
    assert check.is_placeholder
    assert "placeholder" in check.reason.lower()


def test_realistic_density_not_flagged() -> None:
    elements = [
        _col(f"c{i}", float(i * 6000), 0, 8000)
        for i in range(12)
    ] + [
        _beam(f"b{i}", float(i * 6000), 0, float(i * 6000 + 6000), 0, 8000)
        for i in range(11)
    ]
    model = PureStructuralModelSpec(elements=elements, slabs=[])
    check = detect_schematic_placeholder(model, dense_cad=True)
    assert not check.is_placeholder
