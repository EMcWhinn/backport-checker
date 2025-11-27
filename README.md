# Backport checker

Automated tool for verifying that merged pull requests are properly backported to release branches.

## Overview

This script checks PRs merged to the main branch and verifies that backport labels match actual backported PRs. It's designed to help teams maintain consistent backport processes and catch missing backports early.

## Features

- **Fast GitHub REST API integration** - Completes checks in seconds
- **Multiple backport detection methods**:
  - PR number references in backport titles (e.g., `#5186`)
  - Jira ticket matching in PR descriptions and backport titles
  - "Backported to X.X" labels
- **Flexible notifications** - Slack and/or Jira integration
- **Detailed reporting** - Markdown and JSON output formats
- **Customizable version branches** - Configure which release branches to check

## How It Works

The script analyzes PRs merged to your main branch and:

1. Checks for version labels (e.g., "2.6", "2.5", "2.4")
2. Searches for corresponding backport PRs to those version branches
3. Reports two types of issues:
   - **Missing Backport Confirmations**: PRs with version labels but no actual backports
   - **Label Mismatches**: PRs backported but with inconsistent/missing labels

## Installation

### Prerequisites

- Python 3.7+
- GitHub personal access token with `repo` scope
- (Optional) Slack webhook URL for notifications
- (Optional) Jira credentials for notifications

### Setup

1. Clone this repository:
```bash
git clone https://github.com/emcwhinn/backport-checker.git
cd backport-checker
```

2. Install Python dependencies:
```bash
pip install requests python-dotenv
```

3. Configure environment variables:
```bash
cp .env.template .env
```

4. Edit `.env` and add your credentials:
```bash
# Required
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPOSITORY=owner/repo

# Optional - for Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Optional - for Jira notifications
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_USER_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_ISSUE_KEY=PROJ-123
```

5. Make the script executable:
```bash
chmod +x backport-checker.py
```

## Usage

### Basic Usage

Check PRs merged in the last day:
```bash
./backport-checker.py --days 1
```

Check PRs merged in the last week:
```bash
./backport-checker.py --days 7
```

### Save Reports

Save report to a markdown file:
```bash
./backport-checker.py --days 7 --output report.md
```

Save detailed results to JSON:
```bash
./backport-checker.py --days 1 --json results.json
```

### Notifications

Send results to Slack:
```bash
./backport-checker.py --days 1 --notify slack
```

Post results to Jira:
```bash
./backport-checker.py --days 1 --notify jira
```

Send to both Slack and Jira:
```bash
./backport-checker.py --days 1 --notify both
```

## Configuration

### Version Branches

By default, the script checks for backports to versions: **2.6, 2.5, 2.4**

To customize, edit `backport-checker.py` line 41:
```python
self.backport_branches = ["2.6", "2.5", "2.4"]
```

### GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scope: `repo` (Full control of private repositories)
4. Copy the token and add to `.env` file

### Slack Webhook

1. Go to https://api.slack.com/apps
2. Create a new app or select existing
3. Enable "Incoming Webhooks"
4. Add webhook to workspace
5. Copy webhook URL to `.env` file

### Jira API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Create API token
3. Add credentials to `.env` file

## Automation

### GitHub Actions (Recommended)

Create `.github/workflows/backport-checker.yml`:

```yaml
name: Daily Backport Check

on:
  schedule:
    - cron: '0 9 * * 1-5'  # 9 AM UTC, Mon-Fri
  workflow_dispatch:

jobs:
  check-backports:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests python-dotenv

      - name: Check backports
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          ./backport-checker.py --days 1 --notify slack
```

### Cron Job

Add to your crontab:
```bash
# Run daily at 9 AM
0 9 * * * cd /path/to/backport-checker && ./backport-checker.py --days 1 --notify slack
```

## Understanding the Report

### Sample Output

```
# Backport Verification Report

**Date:** 2025-11-27 14:47
**Period:** Last 7 day(s)
**PRs Checked:** 18
**Issues Found:** 4

## ⚠️ Missing Backport Confirmations

These PRs have version labels but no 'Backported to' confirmation:

- **[PR #5146](https://github.com/...)** - Feature update
  - Expected backports: `2.5, 2.6`
  - Confirmed backports: None

## 🔴 Label Mismatches

These PRs have inconsistent version labels:

- **[PR #5148](https://github.com/...)** - CQA update
  - Expected: `` (no version labels)
  - Confirmed: `2.6` (backported anyway)

## ✅ All Backports Verified

No issues found with recent backports.
```

### Report Categories

- **Missing Backport Confirmations**: Action needed - these PRs should be backported
- **Label Mismatches**: Process improvement - labeling was inconsistent but backports exist
- **All Backports Verified**: No issues found

## Troubleshooting

### Script runs very slowly

- The script should complete in seconds using the REST API
- If it's slow, ensure you're using the latest version

### "Not Found" or 404 errors

- Verify `GITHUB_TOKEN` has `repo` scope
- Check `GITHUB_REPOSITORY` format is `owner/repo`
- Ensure token has access to the repository

### Backports not detected

The script looks for backports in three ways:
1. PR number in backport title: `Fix error (#5186)`
2. Jira ticket matching: `[2.6 backport] AAP-12345: ...`
3. "Backported to X.X" labels

Ensure your backport PRs follow at least one of these patterns.

## Contributing

Issues and pull requests are welcome! Please ensure:
- Code follows existing style
- Test your changes with real repositories
- Update documentation as needed

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
- Open an issue on GitHub
- Check existing issues for similar problems

## Acknowledgments

Built to automate backport verification for documentation teams maintaining multiple release branches.
