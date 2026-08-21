from datetime import timedelta

import pytest

from szo import text


class TestFormatDuration:
    def test_under_100_seconds(self):
        assert text.format_duration(0) == "0 s"
        assert text.format_duration(78) == "78 s"
        assert text.format_duration(99) == "99 s"

    def test_under_an_hour(self):
        assert text.format_duration(100) == "1m 40s"
        assert text.format_duration(12 * 60 + 34) == "12m 34s"
        assert text.format_duration(3599) == "59m 59s"

    def test_under_a_day(self):
        assert text.format_duration(3600) == "1h 0m 0s"
        assert text.format_duration(1 * 3600 + 12 * 60 + 34) == "1h 12m 34s"
        assert text.format_duration(86399) == "23h 59m 59s"

    def test_a_day_or_more(self):
        assert text.format_duration(86400) == "1d 0h 0m"
        assert text.format_duration(1 * 86400 + 3 * 3600 + 12 * 60) == "1d 3h 12m"

    def test_rounds_to_whole_seconds(self):
        assert text.format_duration(78.4) == "78 s"
        assert text.format_duration(99.6) == "1m 40s"

    def test_timedelta_input(self):
        assert text.format_duration(timedelta(minutes=12, seconds=34)) == "12m 34s"
        assert text.format_duration(timedelta(days=1, hours=3, minutes=12)) == "1d 3h 12m"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            text.format_duration(-1)


class TestFormatValue:
    def test_bool(self):
        assert text.format_value(True) == "true"
        assert text.format_value(False) == "false"

    def test_list(self):
        assert text.format_value([1, 2, 3]) == "1,2,3"
        assert text.format_value([True, "a"]) == "true,a"

    def test_timedelta_dispatch(self):
        assert text.format_value(timedelta(seconds=78)) == "78 s"

    def test_plain_values(self):
        assert text.format_value("abc") == "abc"
        assert text.format_value(42) == "42"
