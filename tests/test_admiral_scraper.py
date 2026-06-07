import pytest
from unittest.mock import patch, MagicMock
import json


def test_find_working_endpoint_returns_first_success():
    from admiral_scraper import AdmiralScraper
    scraper = AdmiralScraper()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"events": []}

    with patch('requests.get', return_value=mock_resp):
        endpoint = scraper._discover_endpoint()
    assert endpoint is not None
    assert 'kambi' in endpoint or 'admiral' in endpoint


def test_find_working_endpoint_returns_none_when_all_fail():
    from admiral_scraper import AdmiralScraper
    scraper = AdmiralScraper()

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch('requests.get', return_value=mock_resp):
        endpoint = scraper._discover_endpoint()
    assert endpoint is None


def test_canary_hash_detects_schema_change():
    from admiral_scraper import AdmiralScraper
    scraper = AdmiralScraper()

    data_v1 = {"events": [{"id": 1, "name": "test", "odds": []}]}
    data_v2 = {"events": [{"id": 1, "name": "test", "odds": [], "new_field": "x"}]}

    hash1 = scraper._schema_hash(data_v1)
    hash2 = scraper._schema_hash(data_v2)
    assert hash1 != hash2


def test_canary_hash_ignores_value_changes():
    from admiral_scraper import AdmiralScraper
    scraper = AdmiralScraper()

    data_v1 = {"events": [{"id": 1, "name": "Germany", "odds": 2.5}]}
    data_v2 = {"events": [{"id": 2, "name": "Brazil",  "odds": 3.1}]}

    assert scraper._schema_hash(data_v1) == scraper._schema_hash(data_v2)
