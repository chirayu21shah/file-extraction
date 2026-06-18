import pytest
from app import create_app

@pytest.fixture
def client():
    app = create_app(testing=True)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_create_extraction_missing_file(client):
    response = client.post('/extractions', data={"pattern": "*.txt"})
    assert response.status_code == 404