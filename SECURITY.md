# Security Policy

## Supported Versions

The project is pre-1.0; only the `main` branch is currently supported. Security fixes will land there first and be included in the next release tag.

## Reporting a Vulnerability

If you believe you have found a security vulnerability:

1. **Do not** open a public GitHub issue with exploit details.
2. Email: `hello@worlddatafilter.com` with the subject line: `SECURITY: <short summary>`.
3. Include:
   - A minimal reproduction or proof-of-concept.
   - Impact assessment (confidentiality / integrity / availability).
   - Suggested remediation if available.
4. You will receive an acknowledgement within 5 business days.

## Disclosure Process

- Valid reports are triaged promptly; a CVSS-style internal severity scoring is applied.
- A fix or mitigation will be developed and tested.
- A coordinated disclosure date may be agreed if the issue affects downstream consumers.
- Public release notes / CHANGELOG entry will credit the reporter (unless anonymity requested).

## Scope

Elaborlog is a log analysis and novelty alerting CLI/service. The following are generally **out of scope**:
- Vulnerabilities requiring privileged local access beyond the tool's normal execution context.
- Hypothetical issues without a practical exploit path.
- Dependency vulnerabilities already flagged upstream without elaborlog-specific amplification.

## Hardening & Recommendations

Operators deploying the HTTP service should:
- Run behind a reverse proxy with authentication if exposed beyond localhost.
- Keep dependencies updated (Dependabot is enabled for pip + GitHub Actions).
- Monitor and rotate any state snapshots containing potentially sensitive tokenized data.

Thank you for helping keep the project secure.
