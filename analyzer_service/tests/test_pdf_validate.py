from __future__ import annotations

import pytest

from analyzer_service.pdf_validate.validate import validate_pure_model
from analyzer_service.schemas import PureSlabBoxSpec, PureSteelElementSpec, PureStructuralModelSpec


def test_validate_rejects_empty_model() -> None:
    with pytest.raises(Exception):
        PureStructuralModelSpec(elements=[])


def test_validate_ok_minimal_segment() -> None:
    model = PureStructuralModelSpec(
        elements=[
            PureSteelElementSpec(
                id="col_1",
                profile_name="HEB300",
                start_x=0.0,
                start_y=0.0,
                start_z=0.0,
                end_x=0.0,
                end_y=0.0,
                end_z=4000.0,
            )
        ]
    )
    report = validate_pure_model(model)
    assert report.ok
    assert report.element_count == 1


def test_validate_invalid_slab_box() -> None:
    model = PureStructuralModelSpec(
        elements=[
            PureSteelElementSpec(
                id="b1",
                profile_name="IPE200",
                start_x=0.0,
                start_y=0.0,
                start_z=0.0,
                end_x=6000.0,
                end_y=0.0,
                end_z=0.0,
            )
        ],
        slabs=[
            PureSlabBoxSpec(
                id="slab_bad",
                min_x=0.0,
                min_y=0.0,
                min_z=0.0,
                max_x=0.0,
                max_y=1000.0,
                max_z=100.0,
            )
        ],
    )
    report = validate_pure_model(model)
    assert not report.ok
    assert any("slab_bad" in err for err in report.errors)
