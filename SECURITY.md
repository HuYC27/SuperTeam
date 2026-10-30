# Security Policy / 安全策略

## Supported version

Security fixes currently target the latest published SuperTeam release.

## Reporting a vulnerability

Please use GitHub's **Private vulnerability reporting** feature when it is enabled. If that feature is unavailable, open a public issue containing only a request for a private contact channel—do not disclose exploit details publicly.

请优先使用 GitHub 的“私下报告漏洞”功能。如果仓库尚未启用该功能，只提交一个不含技术细节的 Issue，请求维护者提供私密联系方式。

Never include API keys, login cookies, private conversations, local database files, unpublished research materials or participant data in a report. Replace all such values with synthetic examples.

## Security model

SuperTeam's UI is served by a loopback-only local process and protected with a per-run application token. Provider credentials are encrypted with Windows DPAPI. Remote authenticated API requests require HTTPS and reject redirects. These safeguards reduce risk but do not make full computer access safe: only grant the minimum permissions needed for a task and review critical actions before approval.

