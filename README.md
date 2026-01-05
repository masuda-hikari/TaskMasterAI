# TaskMasterAI

**Your AI-Powered Virtual Executive Assistant**

TaskMasterAI is like having a personal assistant that handles your mundane digital chores—intelligently. It doesn't just respond to questions; it takes action on your behalf (with your permission) to automate the repetitive tasks that eat up your productive hours.

## What TaskMasterAI Does

### Email Management
- **Smart Inbox Summarization**: Get daily digests of your unread emails, prioritized by importance
- **AI-Drafted Replies**: Generate contextually appropriate response drafts for common email types
- **Email Triage**: Automatically categorize emails and highlight action items

### Calendar Management
- **Intelligent Scheduling**: Find meeting times that work for all participants automatically
- **Conflict Detection**: Proactively identify and resolve scheduling conflicts
- **Smart Reminders**: Context-aware reminders based on your schedule and priorities

### Task Automation
- **Routine Task Execution**: Automate recurring tasks like weekly reports or status updates
- **Cross-App Integration**: Connect your email, calendar, and task management tools
- **Progress Tracking**: Keep track of tasks and get nudges to stay on schedule

## Key Features

- **AI-Powered Understanding**: Uses advanced AI to understand context, not just keywords
- **Action-Oriented**: Doesn't just advise—actually performs tasks (with your approval)
- **Privacy-First**: Your data stays private. We don't store email content on our servers
- **Confirmation Mode**: Every action requires your explicit approval until you choose otherwise
- **Audit Trail**: Full transparency with detailed logs of all automated actions

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/TaskMasterAI.git
cd TaskMasterAI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up your credentials (see docs/setup_google_api.md)
cp config/.env.example config/.env
# Edit config/.env with your API keys

# Run TaskMasterAI
python -m src.cli
```

## Usage Examples

```bash
# Summarize your inbox
taskmaster summarize inbox

# Find a meeting time
taskmaster schedule "Team sync" --with alice@company.com bob@company.com --duration 30min

# Check your day
taskmaster status today

# Draft a reply
taskmaster draft reply --to "email_id_123"
```

## Pricing

TaskMasterAI is offered as a subscription service, designed to deliver clear ROI for your time investment.

| Plan | Price | Best For |
|------|-------|----------|
| **Personal** | $10/month | Individual professionals looking to reclaim 5+ hours weekly |
| **Pro** | $25/month | Power users with multiple accounts and advanced automation needs |
| **Team** | $15/user/month | Teams needing coordinated scheduling and shared inbox management |
| **Enterprise** | Custom | Organizations requiring on-premise deployment and custom integrations |

### Free Tier
Try TaskMasterAI with limited features:
- 50 email summarizations/month
- 10 scheduling suggestions/month
- No automatic execution (confirmation mode only)

### ROI Calculator
If your time is worth $50/hour and TaskMasterAI saves you 5 hours/week:
- **Monthly savings**: $1,000+ in time value
- **Monthly cost**: $10-25
- **ROI**: 40-100x return on investment

## Privacy & Security

- **OAuth 2.0**: Secure authentication with Google and other providers
- **No Data Storage**: Email content is processed in real-time and not stored
- **Local Processing**: Sensitive operations happen on your machine when possible
- **Audit Logs**: Full transparency into what actions were taken and when
- **Revocable Access**: Disconnect TaskMasterAI from your accounts at any time

## Integrations

### Currently Supported
- Gmail
- Google Calendar

### Coming Soon
- Microsoft Outlook / Office 365
- Slack
- Trello / Asana
- Notion

## Documentation

- [Setup Guide](docs/setup_google_api.md) - Get started with Google API integration
- [CLI Reference](docs/cli_reference.md) - Full command documentation
- [API Documentation](docs/api.md) - For developers building on TaskMasterAI

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Reclaim your time. Let TaskMasterAI handle the rest.**
