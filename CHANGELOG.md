# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/lightsail-network/py-stellar-horizon/compare/v0.1.0...v0.1.1) - 2026-11-27

### Bug Fixes

- Send Decimal path amounts without an exponent ([#2](https://github.com/lightsail-network/py-stellar-horizon/pull/2))
- Never follow redirects, whatever the HTTP client is set to ([#3](https://github.com/lightsail-network/py-stellar-horizon/pull/3))
- Bound the waits a server can ask of a stream ([#4](https://github.com/lightsail-network/py-stellar-horizon/pull/4))
- Send a stream's Accept header whatever the client's headers are ([#5](https://github.com/lightsail-network/py-stellar-horizon/pull/5))
- Keep a stream closed that was closed before it was read ([#6](https://github.com/lightsail-network/py-stellar-horizon/pull/6))
- Start a stream's connections with a fresh backoff once now is resolved ([#7](https://github.com/lightsail-network/py-stellar-horizon/pull/7))
- Refuse an Asset without a code or an issuer ([#8](https://github.com/lightsail-network/py-stellar-horizon/pull/8))
- Refuse a NaN give_up_after and a max_records that is not an int ([#9](https://github.com/lightsail-network/py-stellar-horizon/pull/9))
- Refuse a query in the path of request() ([#10](https://github.com/lightsail-network/py-stellar-horizon/pull/10))
- Make the client's base_url read-only ([#14](https://github.com/lightsail-network/py-stellar-horizon/pull/14))

### Documentation

- Name the key Horizon stores the maintain-liabilities flag under ([#11](https://github.com/lightsail-network/py-stellar-horizon/pull/11))
- Save a stream's cursor in the guide only when there is one ([#12](https://github.com/lightsail-network/py-stellar-horizon/pull/12))
- Say which field names a dump writes ([#13](https://github.com/lightsail-network/py-stellar-horizon/pull/13))

## [0.1.0](https://github.com/lightsail-network/py-stellar-horizon/releases/tag/v0.1.0) - 2026-11-19

### Features

- Add stellar-horizon, a typed client for the Stellar Horizon API, sync and async, checked against Horizon 30.0.1
