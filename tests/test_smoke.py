import backtester


def test_package_imports_with_a_version() -> None:
    assert backtester.__version__ == "0.1.0"
