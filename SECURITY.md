# Security policy

## Supported versions

Security fixes are released for the latest version only. Upgrade to it before reporting
an issue.

## Reporting a vulnerability

Please report vulnerabilities privately, not in a public issue:

- Preferably through
  [GitHub's private vulnerability reporting](https://github.com/lightsail-network/py-stellar-horizon/security/advisories/new).
- Or by email to hi@overcat.dev. For GPG, see https://keybase.io/overcat.

Include the version, a minimal reproduction and what you think the impact is. Don't
include real secret seeds or other private data.

## Scope

Examples of what counts as a vulnerability:

- A response from a server, or a link in one, that makes the client send a request to
  another host.
- A response that makes the client take much more time or memory than its size justifies,
  or raise anything other than the library's documented errors.
- The client sending a transaction twice when it was asked to send it once.
- Credentials or headers of the caller's HTTP client appearing in logs or exceptions.
