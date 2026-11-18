import stellar_horizon


def test_horizon_version_names_a_release() -> None:
    major, minor, patch = stellar_horizon.HORIZON_VERSION.split(".")
    assert int(major) >= 30
    assert minor.isdigit()
    assert patch.isdigit()


def test_the_top_level_has_the_api_and_no_models() -> None:
    # Models are imported from stellar_horizon.models only, so that this namespace
    # stays the short list of what a program calls and catches.
    import stellar_horizon.models  # noqa: PLC0415

    assert not set(stellar_horizon.__all__) & set(stellar_horizon.models.__all__)
    assert len(stellar_horizon.__all__) == 20
