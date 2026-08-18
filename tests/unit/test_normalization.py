from datetime import date

import pytest

from app.domain.rules.normalization import normalize_header, parse_sheet_date


def test_normalizes_headers():
    assert normalize_header(" Noções\nde Primeiros-Socorros ") == "NOCOES_DE_PRIMEIROS_SOCORROS"


@pytest.mark.parametrize("value", ["17/08/2026", "2026-08-17", 46251])
def test_parses_sheet_dates(value):
    assert isinstance(parse_sheet_date(value), date)


def test_invalid_date_is_rejected():
    with pytest.raises(ValueError):
        parse_sheet_date("31/02/2026")
