import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--clr-url", action="store", default="http://localhost:8080",
        help="URL to clear-dissector web application, default as http://localhost:8080"
    )

@pytest.fixture
def clr_url(request):
    return request.config.getoption("--clr-url")