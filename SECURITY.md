# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in pyrh56, please **do not** open a
public issue. Instead, report it privately to the project maintainer.

The maintainer will respond within 5 business days. Once the vulnerability is
confirmed and a fix is prepared, a GitHub Security Advisory will be published
and a patch release issued.

## Scope

Security issues relevant to this project include, but are not limited to:

- Unsafe serial communication patterns that could cause hardware damage
- Bypass of command validation or safety limits
- Protocol parsing vulnerabilities (buffer issues, checksum bypass)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅ |
| < 0.3   | ❌ |
