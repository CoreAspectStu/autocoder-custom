# DevLayer - Quality Gate Board for AutoCoder

## Overview

DevLayer is a quality gate system that sits between UAT Gateway and the Dev board, creating a complete workflow:

```
UAT Test Failure → DevLayer (Triage) → Dev (Fix) → UAT (Retest) → Archive
```

When automated tests fail, bugs automatically flow to DevLayer for prioritization, then to Dev for fixes, then back to UAT for retesting. This creates full traceability across all boards with bidirectional card linking.

## Features

### 1. DevLayer Board
- **Columns**: triage, approved_for_dev, assigned, monitoring
- **Card Types**: 🐛 Bug (from UAT failure), 📋 Issue (manual)
- **Filtering**: By severity (🔴 Critical, 🟡 High, 🟢 Medium, ⚪ Low) and category
- **Card Counts**: Displayed per column

### 2. Triage Interface
- **Severity Assignment**: Critical, High, Medium, Low
- **Category Selection**: UI, Logic, API, Performance, Accessibility
- **Triage Notes**: Add context and investigation findings
- **Approve/Dismiss**: Send to Dev or dismiss as false positive

### 3. Bidirectional Card Linking
- **UAT Bug Card ←→ DevLayer Bug Card**
- **DevLayer Bug Card ←→ Dev Card**
- **Dev Card ←→ UAT Bug Card** (back-reference)
- **One-Click Navigation**: Jump between linked cards
- **Visual Indicators**: See card relationships at a glance

### 4. Automated Triggers
- **UAT Failure** → Auto-create DevLayer bug card
- **DevLayer Approval** → Auto-create Dev card
- **Dev Complete** → Auto-trigger UAT retest
- **UAT Retest Pass** → Archive all linked cards
- **UAT Retest Fail** → Update cards, return to Dev

### 5. Smart Retesting
- Only retest scenarios affected by code changes
- Calculate impact using code coverage data
- Skip unrelated scenarios to save time
- Display which scenarios are being retested
- Aggregate results across all affected scenarios

### 6. Quality Pipeline Dashboard
- **Real-time Metrics**: UAT pass rate, DevLayer triage count, Dev active cards
- **Pipeline Velocity**: Average time in each stage
- **Visual Flow Diagram**: See card movement between stages
- **Filters**: By project, severity, assignee
- **Export**: Download as CSV/JSON

### 7. Slack Notifications
- UAT test failure (with evidence)
- Bug approved for Dev
- Dev card assigned
- Dev card complete
- UAT retest completes
- Daily digest of pipeline activity

### 8. n8n Workflow Integration
- **Workflow 1**: UAT failure → DevLayer card creation
- **Workflow 2**: DevLayer approval → Dev card creation
- **Workflow 3**: Dev complete → UAT retest trigger
- **Webhook Endpoints**: Manual trigger for each workflow
- **Error Handling**: Retry logic for failed executions
- **Execution History**: Track in n8n dashboard

## Installation

### 1. Enable the Module

The DevLayer module is included in AutoCoder at:
```
/home/stu/projects/autocoder/custom/devlayer/
```

### 2. Install Dependencies

```bash
cd /home/stu/projects/autocoder
source venv/bin/activate
pip install aiohttp
```

### 3. Initialize Database

The database is created automatically on first run. To initialize manually:

```python
from custom.devlayer.database import DevLayerDatabase

db = DevLayerDatabase("devlayer.db")
db.init_database()
```

### 4. Configure AutoCoder API

Add the DevLayer routers to your FastAPI application:

```python
from custom.devlayer.api import (
    create_devlayer_router,
    create_pipeline_router,
    create_card_links_router,
)

# Add routers to your app
app.include_router(create_devlayer_router())
app.include_router(create_pipeline_router())
app.include_router(create_card_links_router())
```

### 5. Set Up n8n Workflows

Import the workflow definitions:

```bash
# Import workflows to n8n
curl -X POST http://localhost:5678/rest/workflows/import \
  -H "Content-Type: application/json" \
  -d @custom/devlayer/n8n/workflows.json
```

## Usage

### Programmatic Usage

```python
from custom.devlayer import DevLayerManager, DevLayerConfig, TestEvidence, Severity, Category

# Configure manager
config = DevLayerConfig(
    db_path="devlayer.db",
    uat_gateway_url="http://localhost:8889",
    dev_board_url="http://localhost:4000",
    enable_slack=True,
    enable_n8n=True,
    n8n_webhook_url="http://localhost:5678/webhook/devlayer",
    slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
)

manager = DevLayerManager(config, project_id="my-project")

# Create bug card from UAT failure
evidence = TestEvidence(
    scenario_id="SCENARIO-123",
    error_message="Button not responding to click",
    steps_to_reproduce=[
        "1. Navigate to /home",
        "2. Click 'Submit' button",
        "3. Observe: nothing happens",
    ],
    screenshot_path="/output/scenario-123-failed.png",
    log_path="/output/scenario-123.log",
)

card = await manager.create_uat_bug_card(evidence)

# Triage the card
await manager.triage_card(
    card_id=card.id,
    severity=Severity.HIGH,
    category=Category.UI,
    triage_notes="Button event handler not attached in production build",
    triaged_by="user@example.com",
)

# Approve for Dev
await manager.approve_for_dev(
    card_id=card.id,
    approved_by="user@example.com",
    assignee="developer@example.com",
)

# When Dev completes, trigger retest
result = await manager.on_dev_complete(
    dev_card_id="dev-abc123",
    completed_by="developer@example.com",
)

# Handle retest completion
await manager.on_uat_retest_complete(
    devlayer_card_id=card.id,
    retest_result={"passed": True},
)
```

### API Usage

#### Create Bug Card from UAT Failure
```bash
POST /api/devlayer/bug
Content-Type: application/json

{
  "evidence": {
    "scenario_id": "SCENARIO-123",
    "error_message": "Button not responding",
    "steps_to_reproduce": ["Step 1", "Step 2"],
    "screenshot_path": "/output/screenshot.png"
  },
  "title": "UAT Bug: Button not responding",
  "uat_card_id": "uat-456"
}
```

#### Triage Bug Card
```bash
POST /api/devlayer/triage/{card_id}
Content-Type: application/json

{
  "severity": "High",
  "category": "UI",
  "triage_notes": "Investigation shows missing event handler",
  "triaged_by": "user@example.com"
}
```

#### Approve for Dev
```bash
POST /api/devlayer/approve/{card_id}
Content-Type: application/json

{
  "approved_by": "user@example.com",
  "assignee": "developer@example.com"
}
```

#### Get Board Stats
```bash
GET /api/devlayer/stats
```

#### Get Pipeline Dashboard
```bash
GET /api/pipeline/dashboard
```

#### Get Linked Cards
```bash
GET /api/cards/{card_id}/linked
```

## Database Schema

### devlayer_cards
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Card ID |
| uat_card_id | TEXT | Linked UAT card |
| dev_card_id | TEXT | Linked Dev card |
| severity | TEXT | Critical/High/Medium/Low |
| category | TEXT | UI/Logic/API/Performance/A11Y |
| triage_notes | TEXT | Triage notes |
| triaged_by | TEXT | Who triaged |
| triaged_at | TIMESTAMP | When triaged |
| approved_by | TEXT | Who approved |
| approved_at | TIMESTAMP | When approved |
| status | TEXT | triage/approved_for_dev/assigned/monitoring |
| title | TEXT | Card title |
| description | TEXT | Card description |
| evidence_json | TEXT | JSON evidence |
| created_at | TIMESTAMP | Created time |
| updated_at | TIMESTAMP | Updated time |

### card_links
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Link ID |
| from_card_id | TEXT | Source card |
| to_card_id | TEXT | Target card |
| from_board | TEXT | Source board (uat/devlayer/dev) |
| to_board | TEXT | Target board |
| link_type | TEXT | uat_to_devlayer/devlayer_to_dev/uat_to_dev |
| created_at | TIMESTAMP | Link time |

### pipeline_events
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Event ID |
| event_type | TEXT | uat_failure/devlayer_approval/dev_complete/uat_retest |
| card_id | TEXT | Related card |
| from_stage | TEXT | uat/devlayer/dev |
| to_stage | TEXT | uat/devlayer/dev |
| result | TEXT | pass/fail/archive/return |
| evidence_json | TEXT | Event evidence |
| created_at | TIMESTAMP | Event time |

### archived_cards
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Archive ID |
| devlayer_card_id | TEXT | Original card ID |
| uat_card_id | TEXT | Linked UAT card |
| dev_card_id | TEXT | Linked Dev card |
| card_data_json | TEXT | Full card data |
| archived_at | TIMESTAMP | Archive time |

## Workflow Examples

### Complete Bug Lifecycle

```
1. UAT Test Fails
   ↓
2. POST /api/devlayer/bug
   - Creates DevLayer card in "triage"
   - Links to UAT card
   - Sends Slack notification
   - Triggers n8n workflow
   ↓
3. DevLayer: Triage
   - Assign severity: High
   - Assign category: UI
   - Add triage notes
   ↓
4. DevLayer: Approve for Dev
   - POST /api/devlayer/approve/{card_id}
   - Creates Dev card
   - Links all three cards
   - Moves to "assigned"
   - Sends Slack notification
   ↓
5. Dev: Implement Fix
   - Developer works on Dev card
   - Marks as complete
   ↓
6. POST /api/devlayer/dev/complete/{dev_card_id}
   - Calculates affected scenarios
   - Triggers UAT retest
   ↓
7. UAT: Retest
   - Runs affected scenarios only
   - Returns results
   ↓
8. POST /api/devlayer/uat/retest/{devlayer_card_id}
   ↓
   ├─ PASS → Archive all cards
   │   - Move to archived_cards table
   │   - Send success notification
   │
   └─ FAIL → Return to Dev
       - Update with new evidence
       - Move back to "triage"
       - Send failure notification
```

## UI Integration

### Three-Column View

The DevLayer board integrates with the existing AutoCoder Kanban UI:

```
┌─────────────┬─────────────┬─────────────┐
│   UAT       │  DevLayer   │    Dev      │
├─────────────┼─────────────┼─────────────┤
│  planned    │  triage     │  backlog    │
│  running    │  approved   │  in_progress│
│  passed     │  assigned   │  code_review│
│  failed     │  monitoring │  testing    │
│  bugs       │             │  complete   │
└─────────────┴─────────────┴─────────────┘
```

### Card Details Panel

When a card is selected, show:
- **Linked Cards**: Click to navigate
- **Severity Badge**: Color-coded
- **Category Badge**: Icon
- **Evidence**: Screenshots, logs
- **Pipeline History**: All movements

### Pipeline Dashboard Button

Top navigation button shows:
- Cards in each stage
- Pass rate percentage
- Average time in pipeline
- Recent events

## Testing

### Unit Tests

```python
import pytest
from custom.devlayer import DevLayerManager, TestEvidence

@pytest.mark.asyncio
async def test_create_bug_card():
    manager = DevLayerManager(config, "test")
    evidence = TestEvidence(
        scenario_id="test-1",
        error_message="Test error",
        steps_to_reproduce=["Step 1"],
    )
    card = await manager.create_uat_bug_card(evidence)
    assert card.id is not None
    assert card.status == DevLayerStatus.TRIAGE
```

### Integration Tests

```bash
# Test complete workflow
curl -X POST http://localhost:8889/api/devlayer/bug \
  -d @test/evidence.json

# Get board stats
curl http://localhost:8889/api/devlayer/stats

# Get pipeline metrics
curl http://localhost:8889/api/pipeline/dashboard
```

## Monitoring

### Metrics

Track these metrics:
- UAT pass rate
- DevLayer triage time
- Dev fix time
- End-to-end cycle time
- Cards archived vs returned

### Alerts

Set up alerts for:
- High severity bugs in triage > 1 hour
- Cards in assigned > 24 hours
- UAT retest failure rate > 20%
- Pipeline velocity degradation

## Troubleshooting

### Cards Not Creating

1. Check database permissions
2. Verify API endpoints are registered
3. Check n8n webhook is reachable
4. Review AutoCoder logs

### Links Not Working

1. Verify card IDs exist
2. Check link_type values
3. Review database for orphaned links
4. Test get_linked_cards endpoint

### Retest Not Triggering

1. Check Dev card ID mapping
2. Verify UAT Gateway is running
3. Review n8n workflow execution
4. Check API connectivity

## License

Part of the AutoCoder project.

## Support

For issues or questions, contact the AutoCoder team or check the documentation at:
```
/home/stu/docs/projects/autocoder/devlayer-integration.md
```
