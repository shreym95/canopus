import pytest
from agents.searcher.base import parse_salary_lpa, _parse_cookies


class TestParseSalaryLpa:
    @pytest.mark.parametrize("text,expected", [
        ("35 LPA",            35.0),
        ("35-50 LPA",         35.0),
        ("₹40L",              40.0),
        ("40 lakhs",          40.0),
        ("40 Lakh",           40.0),
        ("35L - 50L",         35.0),
        ("35,00,000",         None),   # rupees without LPA keyword → None
        ("",                  None),
        (None,                None),
        ("Not disclosed",     None),
        ("12.5 LPA",          12.5),
        ("1.5–3 LPA",         1.5),
        ("70 lpa",            70.0),
        ("25 L",              25.0),
    ])
    def test_parse(self, text, expected):
        assert parse_salary_lpa(text) == expected


class TestParseCookies:
    def test_valid_cookies(self):
        raw = [{"name": "session", "value": "abc123", "domain": ".linkedin.com"}]
        result = _parse_cookies(raw)
        assert len(result) == 1
        assert result[0]["name"] == "session"
        assert result[0]["value"] == "abc123"
        assert result[0]["sameSite"] == "Lax"   # default

    def test_samesite_passthrough(self):
        raw = [{"name": "x", "value": "y", "sameSite": "Strict"}]
        assert _parse_cookies(raw)[0]["sameSite"] == "Strict"

    def test_invalid_samesite_defaults_to_lax(self):
        raw = [{"name": "x", "value": "y", "sameSite": "invalid_value"}]
        assert _parse_cookies(raw)[0]["sameSite"] == "Lax"

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="missing 'name'"):
            _parse_cookies([{"value": "abc"}])

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="missing 'name'"):
            _parse_cookies([{"name": "", "value": "abc"}])

    def test_missing_value_raises(self):
        with pytest.raises(ValueError, match="missing 'value'"):
            _parse_cookies([{"name": "sess"}])

    def test_not_a_list_raises(self):
        with pytest.raises(ValueError, match="JSON array"):
            _parse_cookies({"name": "x", "value": "y"})

    def test_non_dict_entry_raises(self):
        with pytest.raises(ValueError, match="not an object"):
            _parse_cookies(["not_a_dict"])

    def test_boolean_fields_coerced(self):
        raw = [{"name": "x", "value": "y", "secure": 1, "httpOnly": 0}]
        result = _parse_cookies(raw)
        assert result[0]["secure"] is True
        assert result[0]["httpOnly"] is False

    def test_empty_list(self):
        assert _parse_cookies([]) == []

    def test_domain_cast_to_str(self):
        raw = [{"name": "x", "value": "y", "domain": 12345}]
        result = _parse_cookies(raw)
        assert result[0]["domain"] == "12345"
