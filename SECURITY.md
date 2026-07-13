# Security policy

## Supported versions

Security fixes are made on the latest release line. Update to the newest supported release and
current patch versions of dependencies before reporting a resolved upstream issue.

| Version | Supported |
| --- | ---: |
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Do not open a public issue. Use the repository's private vulnerability reporting feature. If it
is unavailable, contact the maintainer privately through the address listed in the repository
owner's GitHub profile and include “Security: Claude Code Gateway” in the subject.

Include:

- the affected version or commit;
- operating system and Python version;
- a minimal reproduction with fake credentials and non-sensitive prompts;
- impact and any known mitigations.

Never send a live API key. Revoke exposed credentials at the provider before reporting. Expect an
acknowledgment within seven days; disclosure timing will be coordinated after a fix is available.

## Scope and trust boundary

The supported default is a single-user gateway bound to loopback. Exposing it to a LAN, the
internet, containers on an untrusted network, or multiple users changes the threat model and
requires controls outside this repository: TLS, firewall policy, managed secrets, token rotation,
rate limits, audit and retention rules, dependency scanning, and incident response.

Security reports about LiteLLM, Claude Code, or a model provider should also be reported to the
upstream project when the issue is not caused by this launcher.

Project-local VS Code configuration and its backup contain the local proxy token. They are ignored
by Git but remain plaintext files readable by the current operating-system user. Treat both like
`.env`, never attach them to issues, and rotate the proxy token after accidental disclosure.
