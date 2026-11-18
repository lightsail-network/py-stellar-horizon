import stellar_horizon


def test_horizon_version_names_a_release() -> None:
    major, minor, patch = stellar_horizon.HORIZON_VERSION.split(".")
    assert int(major) >= 30
    assert minor.isdigit()
    assert patch.isdigit()
