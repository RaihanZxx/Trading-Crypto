# Security Policy

## Supported Versions

Currently, only the latest version of this project is being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability within this project, please send an email to raihanzxx@example.com. All security vulnerabilities will be promptly addressed.

Please do not publicly disclose the vulnerability until it has been addressed by the team.

## Security Practices

### API Keys and Secrets
- All API keys and secrets should be stored in environment variables, not in the code
- The .env file is included in .gitignore to prevent accidental commits
- Use strong, unique passwords for all services

### Data Protection
- All data is stored locally in SQLite database
- No personal information is collected or stored
- Database files should not be shared publicly

### Network Security
- All API calls use HTTPS endpoints
- Input validation is performed on all external data
- Error messages do not expose sensitive information

### Dependency Management
- Dependencies are regularly updated to address known vulnerabilities
- Use `pip-audit` or similar tools to check for vulnerable dependencies