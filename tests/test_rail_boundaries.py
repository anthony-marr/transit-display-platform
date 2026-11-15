"""Edge cases for rail alerts, independent of the database and live feeds."""

import copy

import pytest

from transit_platform import rail_analytics as ra


def prediction(minutes, station="E03", group="1"):
    return {
        "station_code": station, "station_name": "Test Station",
        "line": "GR", "minutes": minutes, "group": group,
    }


@pytest.mark.parametrize("headway,expected", [(2, True), (3, True), (4, False)])
def test_bunch_threshold_is_inclusive(headway, expected):
    records = ra.snapshot_headways([prediction("1"), prediction(str(1 + headway))])
    assert bool(ra.find_bunches(records)) is expected


@pytest.mark.parametrize("headway,expected", [(17, False), (18, True), (19, True)])
def test_gap_threshold_is_inclusive(headway, expected):
    records = ra.snapshot_headways([prediction("1"), prediction(str(1 + headway))])
    assert bool(ra.find_gaps(records)) is expected


def test_single_trains_at_different_stations_do_not_form_a_bunch():
    records = ra.snapshot_headways([
        prediction("2", station="E03"), prediction("3", station="E04"),
    ])
    assert len(records) == 2
    assert ra.find_bunches(records) == []
    assert ra.find_gaps(records) == []


def test_arriving_and_boarding_trains_keep_zero_headway():
    records = ra.snapshot_headways([prediction("ARR"), prediction("BRD")])
    assert records[0]["etas"] == [0, 0]
    assert ra.find_bunches(records)[0]["headway"] == 0


def test_unknown_estimates_are_skipped_without_mutating_input():
    rows = [prediction("9"), prediction("---"), prediction("2")]
    original = copy.deepcopy(rows)
    records = ra.snapshot_headways(rows)
    assert records[0]["etas"] == [2, 9]
    assert records[0]["headways"] == [7]
    assert rows == original
