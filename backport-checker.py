#!/usr/bin/env python3
"""
Backport Verification Script

This script checks PRs merged to main and verifies that backport labels
match actual backported PRs.

Usage:
    python backport-checker.py --days 7 --notify slack
    python backport-checker.py --days 1 --notify jira
    python backport-checker.py --days 1 --notify both

Requirements:
    pip install requests python-dotenv
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta, timezone
from base64 import b64encode
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed.")
    print("Please run: pip install requests python-dotenv")
    sys.exit(1)


class BackportChecker:
    """Main class for checking backports using GitHub REST API"""

    def __init__(self, repo_name: str, github_token: str, days_back: int = 1):
        self.repo_name = repo_name
        self.github_token = github_token
        self.days_back = days_back
        self.backport_branches = ["2.6", "2.5", "2.4"]
        self.api_base = "https://api.github.com"
        self.headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make a GitHub API request"""
        url = f"{self.api_base}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def check_backports(self) -> Dict:
        """Check recent PRs for backport status"""
        since_date = datetime.now(timezone.utc) - timedelta(days=self.days_back)

        results = {
            'checked_prs': [],
            'missing_backports': [],
            'label_mismatches': [],
            'success_count': 0,
            'total_count': 0,
            'date': datetime.now().isoformat(),
            'latest_commit': None,
            'base_branch': None
        }

        print(f"Checking PRs merged since {since_date.strftime('%Y-%m-%d %H:%M')}")

        # Try main branch first, then master
        for base_branch in ['main', 'master']:
            try:
                # Get merged PRs
                params = {
                    'state': 'closed',
                    'base': base_branch,
                    'sort': 'updated',
                    'direction': 'desc',
                    'per_page': 100
                }

                pulls = self._make_request(f'/repos/{self.repo_name}/pulls', params)

                if not pulls:
                    continue

                # Get latest commit SHA from this branch
                try:
                    branch_info = self._make_request(f'/repos/{self.repo_name}/branches/{base_branch}')
                    results['latest_commit'] = branch_info['commit']['sha'][:7]
                    results['base_branch'] = base_branch
                except:
                    pass

                print(f"Found {len(pulls)} recent PRs on {base_branch} branch")

                for pr in pulls:
                    # Skip if not merged or outside date range
                    if not pr.get('merged_at'):
                        continue

                    merged_at = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00'))
                    if merged_at < since_date:
                        continue

                    results['total_count'] += 1
                    pr_info = self._analyze_pr(pr)
                    results['checked_prs'].append(pr_info)

                    # Check for issues
                    if set(pr_info['expected_backports']) != set(pr_info['backported_to']):
                        results['label_mismatches'].append(pr_info)

                    if pr_info['expected_backports'] and not pr_info['backported_to']:
                        results['missing_backports'].append(pr_info)

                    if not results['missing_backports'] and not results['label_mismatches']:
                        results['success_count'] += 1

                    print(f"  Checked PR #{pr['number']}: {pr['title'][:60]}...")

                break  # If we found PRs, don't try other branch

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    continue
                raise

        print(f"\nTotal PRs checked: {results['total_count']}")
        print(f"Issues found: {len(results['missing_backports']) + len(results['label_mismatches'])}")

        return results

    def _analyze_pr(self, pr: Dict) -> Dict:
        """Analyze a single PR for backport information"""
        import re

        pr_info = {
            'number': pr['number'],
            'title': pr['title'],
            'merged_at': pr['merged_at'],
            'url': pr['html_url'],
            'labels': [label['name'] for label in pr.get('labels', [])],
            'backported_to': [],
            'expected_backports': []
        }

        # Check labels for expected backports
        for label in pr.get('labels', []):
            label_name = label['name']
            if label_name.startswith('Backported to '):
                version = label_name.replace('Backported to ', '')
                pr_info['backported_to'].append(version)
            elif any(label_name == version for version in self.backport_branches):
                pr_info['expected_backports'].append(label_name)

        # Extract Jira ticket from PR body if present (e.g., "AAP-12345")
        jira_ticket = None
        pr_body = pr.get('body', '') or ''
        jira_match = re.search(r'AAP-\d+', pr_body)
        if jira_match:
            jira_ticket = jira_match.group(0)

        # Check for backport PRs that reference this PR
        # Look for merged PRs to version branches that mention this PR number or Jira ticket
        for version in self.backport_branches:
            try:
                # Search for PRs merged to this version branch
                params = {
                    'state': 'closed',
                    'base': version,
                    'per_page': 20
                }
                backport_prs = self._make_request(f'/repos/{self.repo_name}/pulls', params)

                # Check if any of these PRs reference the original PR number or Jira ticket
                for backport_pr in backport_prs:
                    if not backport_pr.get('merged_at'):
                        continue

                    backport_title = backport_pr.get('title', '')

                    # Check for PR number reference (e.g., "#5146" or "(#5146)")
                    if f"#{pr['number']}" in backport_title or f"(#{pr['number']})" in backport_title:
                        if version not in pr_info['backported_to']:
                            pr_info['backported_to'].append(version)
                        break

                    # Check for Jira ticket reference if we found one
                    if jira_ticket and jira_ticket in backport_title:
                        if version not in pr_info['backported_to']:
                            pr_info['backported_to'].append(version)
                        break
            except Exception as e:
                # Continue even if we can't check backport PRs for a specific version
                pass

        return pr_info

    def generate_report(self, results: Dict) -> str:
        """Generate a markdown report"""
        report = "# Backport Verification Report\n\n"
        report += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\\n"
        report += f"**Period:** Last {self.days_back} day(s)\\n"

        # Add latest commit info if available
        if results.get('latest_commit') and results.get('base_branch'):
            report += f"**Branch:** {results['base_branch']}\\n"
            report += f"**Latest Commit:** {results['latest_commit']}\\n"

        report += f"**PRs Checked:** {results['total_count']}\\n"
        report += f"**Issues Found:** {len(results['missing_backports']) + len(results['label_mismatches'])}\\n\\n"

        if results['missing_backports']:
            report += "## ⚠️ Missing Backport Confirmations\n\n"
            report += "These PRs have version labels but no 'Backported to' confirmation:\n\n"
            for pr in results['missing_backports']:
                report += f"- **[PR #{pr['number']}]({pr['url']})** - {pr['title']}\n"
                report += f"  - Expected backports: `{', '.join(pr['expected_backports'])}`\n"
                report += f"  - Confirmed backports: None\n"
                report += "\n"

        if results['label_mismatches']:
            report += "## 🔴 Label Mismatches\n\n"
            report += "These PRs have inconsistent version labels:\n\n"
            for pr in results['label_mismatches']:
                report += f"- **[PR #{pr['number']}]({pr['url']})** - {pr['title']}\n"
                report += f"  - Expected: `{', '.join(pr['expected_backports'])}`\n"
                report += f"  - Confirmed: `{', '.join(pr['backported_to']) if pr['backported_to'] else 'None'}`\n"
                report += "\n"

        if not results['missing_backports'] and not results['label_mismatches']:
            report += "## ✅ All Backports Verified\n\n"
            report += "No issues found with recent backports. All version labels match backport confirmations.\n"

        return report


class NotificationHandler:
    """Handle notifications to Slack and Jira"""

    @staticmethod
    def send_slack(results: Dict, webhook_url: str) -> bool:
        """Send notification to Slack"""
        issues_count = len(results['missing_backports']) + len(results['label_mismatches'])

        # Determine color based on results
        if issues_count == 0:
            color = "good"
            emoji = "✅"
        elif issues_count < 5:
            color = "warning"
            emoji = "⚠️"
        else:
            color = "danger"
            emoji = "🔴"

        # Build message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Backport Verification Report"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Date:*\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*PRs Checked:*\n{results['total_count']}"
                    }
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Issues Found:*\n{issues_count}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Missing Backports:*\n{len(results['missing_backports'])}"
                    }
                ]
            }
        ]

        # Add details for issues
        if results['missing_backports']:
            missing_text = "*Missing Backport Confirmations:*\n"
            for pr in results['missing_backports'][:5]:  # Show first 5
                missing_text += f"• <{pr['url']}|PR #{pr['number']}>: {pr['title'][:50]}\n"
            if len(results['missing_backports']) > 5:
                missing_text += f"_...and {len(results['missing_backports']) - 5} more_\n"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": missing_text
                }
            })

        if results['label_mismatches']:
            mismatch_text = "*Label Mismatches:*\n"
            for pr in results['label_mismatches'][:5]:  # Show first 5
                mismatch_text += f"• <{pr['url']}|PR #{pr['number']}>: {pr['title'][:50]}\n"
            if len(results['label_mismatches']) > 5:
                mismatch_text += f"_...and {len(results['label_mismatches']) - 5} more_\n"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": mismatch_text
                }
            })

        payload = {
            "attachments": [{
                "color": color,
                "blocks": blocks
            }]
        }

        try:
            response = requests.post(webhook_url, json=payload)
            if response.status_code == 200:
                print("✓ Slack notification sent successfully")
                return True
            else:
                print(f"✗ Failed to send Slack notification: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Error sending Slack notification: {e}")
            return False

    @staticmethod
    def send_jira(results: Dict, jira_config: Dict) -> bool:
        """Post comment to Jira issue"""
        issues_count = len(results['missing_backports']) + len(results['label_mismatches'])

        if issues_count == 0 and not jira_config.get('always_post', False):
            print("ℹ No issues found, skipping Jira notification")
            return True

        # Create Jira formatted comment
        comment_lines = [
            f"h2. Backport Verification Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"*PRs Checked:* {results['total_count']}",
            f"*Issues Found:* {issues_count}",
            ""
        ]

        if results['missing_backports']:
            comment_lines.append("h3. ⚠️ Missing Backport Confirmations")
            comment_lines.append("")
            for pr in results['missing_backports']:
                comment_lines.append(f"* [PR #{pr['number']}|{pr['url']}] - {pr['title']}")
                comment_lines.append(f"** Expected: {', '.join(pr['expected_backports'])}")
                comment_lines.append("")

        if results['label_mismatches']:
            comment_lines.append("h3. 🔴 Label Mismatches")
            comment_lines.append("")
            for pr in results['label_mismatches']:
                comment_lines.append(f"* [PR #{pr['number']}|{pr['url']}] - {pr['title']}")
                comment_lines.append(f"** Expected: {', '.join(pr['expected_backports'])}")
                confirmed = ', '.join(pr['backported_to']) if pr['backported_to'] else 'None'
                comment_lines.append(f"** Confirmed: {confirmed}")
                comment_lines.append("")

        if not results['missing_backports'] and not results['label_mismatches']:
            comment_lines.append("h3. ✅ All Backports Verified")
            comment_lines.append("")
            comment_lines.append("No issues found with recent backports.")

        comment_text = "\n".join(comment_lines)

        # Prepare API request
        jira_url = f"{jira_config['base_url']}/rest/api/3/issue/{jira_config['issue_key']}/comment"
        auth_string = f"{jira_config['email']}:{jira_config['api_token']}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = b64encode(auth_bytes).decode('utf-8')

        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json'
        }

        # Use Atlassian Document Format
        payload = {
            'body': {
                'type': 'doc',
                'version': 1,
                'content': [{
                    'type': 'paragraph',
                    'content': [{
                        'type': 'text',
                        'text': comment_text
                    }]
                }]
            }
        }

        try:
            response = requests.post(jira_url, headers=headers, json=payload)
            if response.status_code == 201:
                print("✓ Jira comment posted successfully")
                return True
            else:
                print(f"✗ Failed to post Jira comment: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Error posting to Jira: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Check backport status of merged PRs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check last 7 days and send to Slack
  python backport-checker.py --days 7 --notify slack

  # Check last day and post to Jira
  python backport-checker.py --days 1 --notify jira

  # Check and send to both
  python backport-checker.py --days 1 --notify both

  # Just check and display report
  python backport-checker.py --days 1

Environment variables required:
  GITHUB_TOKEN - GitHub personal access token
  GITHUB_REPOSITORY - Repository name (e.g., "ansible/aap-docs")

For Slack notifications:
  SLACK_WEBHOOK_URL - Slack incoming webhook URL

For Jira notifications:
  JIRA_BASE_URL - Jira instance URL (e.g., "https://yourcompany.atlassian.net")
  JIRA_USER_EMAIL - Your Jira email
  JIRA_API_TOKEN - Jira API token
  JIRA_ISSUE_KEY - Issue to comment on (e.g., "PROJ-123")
        """
    )

    parser.add_argument(
        '--days',
        type=int,
        default=1,
        help='Number of days to look back (default: 1)'
    )

    parser.add_argument(
        '--notify',
        choices=['slack', 'jira', 'both', 'none'],
        default='none',
        help='Send notifications to Slack, Jira, or both'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Save report to file (markdown format)'
    )

    parser.add_argument(
        '--json',
        type=str,
        help='Save detailed results to JSON file'
    )

    args = parser.parse_args()

    # Load environment variables from .env file if it exists
    load_dotenv()

    # Get required environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    repo_name = os.getenv('GITHUB_REPOSITORY', 'ansible/aap-docs')

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Please set it to your GitHub personal access token")
        sys.exit(1)

    print(f"Backport Checker for {repo_name}")
    print("=" * 60)

    # Run the checker
    checker = BackportChecker(repo_name, github_token, args.days)
    results = checker.check_backports()

    # Generate and display report
    report = checker.generate_report(results)
    print("\n" + report)

    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\n✓ Report saved to {args.output}")

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"✓ Detailed results saved to {args.json}")

    # Send notifications
    notifier = NotificationHandler()

    if args.notify in ['slack', 'both']:
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if webhook_url:
            notifier.send_slack(results, webhook_url)
        else:
            print("⚠ SLACK_WEBHOOK_URL not set, skipping Slack notification")

    if args.notify in ['jira', 'both']:
        jira_config = {
            'base_url': os.getenv('JIRA_BASE_URL'),
            'email': os.getenv('JIRA_USER_EMAIL'),
            'api_token': os.getenv('JIRA_API_TOKEN'),
            'issue_key': os.getenv('JIRA_ISSUE_KEY')
        }

        if all(jira_config.values()):
            notifier.send_jira(results, jira_config)
        else:
            print("⚠ Jira configuration incomplete, skipping Jira notification")
            print("  Required: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN, JIRA_ISSUE_KEY")


if __name__ == '__main__':
    main()
