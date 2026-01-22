# Authentication Settings Customization

**CUSTOM FEATURE** - This is a custom addition to AutoCoder that adds flexible authentication method switching via the web UI.

## What This Adds

A new authentication settings panel on the `/status` page that allows switching between:
1. **Claude Login** - Uses `claude login` credentials (default)
2. **API Key** - Uses Anthropic API key for pay-per-use

## Why This Is Needed

By default, AutoCoder requires running `claude login` before use. This customization adds flexibility to:
- Switch to API key authentication without editing files manually
- Manage auth settings through a web UI
- Store API keys securely in the `.env` file
- Switch back to Claude login easily when needed

## Important Implementation Notes

When working with JavaScript inside Python triple-quoted strings (as in `server/routers/status.py`):

1. **Escape newlines:** Use `'\\n'` instead of `'\n'` in JavaScript strings, otherwise Python interprets the backslash-n as a literal newline character
2. **Avoid Unicode:** Do not use Unicode emoji or special characters in JavaScript code - they can cause encoding issues and "Invalid or unexpected token" errors. Use plain ASCII text instead.
3. **No hardcoded attributes:** Don't use `checked` attribute or inline `onclick` handlers on form elements that JavaScript needs to control dynamically
4. **Let JavaScript control state:** Remove all hardcoded HTML attributes that conflict with JavaScript state management

## Files Modified

### 1. Backend Files

#### `server/schemas.py`
**Lines Modified:** ~366-390

Added fields to `SettingsResponse` and `SettingsUpdate` schemas:

```python
class SettingsResponse(BaseModel):
    """Response schema for global settings."""
    yolo_mode: bool = False
    model: str = DEFAULT_MODEL
    glm_mode: bool = False
    auth_method: Literal["claude_login", "api_key"] = "claude_login"  # CUSTOM
    api_key_configured: bool = False  # CUSTOM

class SettingsUpdate(BaseModel):
    """Request schema for updating global settings."""
    yolo_mode: bool | None = None
    model: str | None = None
    auth_method: Literal["claude_login", "api_key"] | None = None  # CUSTOM
    api_key: str | None = None  # CUSTOM
```

#### `server/routers/settings.py`
**Modified:** Added auth_config import and extended GET/PATCH endpoints

Changes made:
1. Added import: `from custom.auth_config import get_current_auth_method, set_auth_method`
2. Extended `get_settings()` to return `auth_method` and `api_key_configured`
3. Extended `update_settings()` to handle `auth_method` and `api_key` updates

**Search for:** `# CUSTOM:` comments to find the additions

#### `server/routers/status.py`
**Modified:** Added auth settings UI panel and JavaScript

Changes made:
1. Added CSS styles for `.auth-settings`, `.auth-form`, `.radio-group`, etc. (search for `/* CUSTOM: Auth Settings Panel */`)
2. Added HTML panel after header with radio buttons and API key input (search for `<!-- CUSTOM: Authentication Settings -->`)
3. Added JavaScript functions: `loadAuthSettings()`, event handlers for save button (search for `// CUSTOM: Authentication Settings`)

### 2. New Custom Files

#### `custom/auth_config.py` (NEW)
**Purpose:** Utility module for managing authentication settings in `.env` file

**Functions:**
- `get_env_file_path()` - Get path to .env file
- `read_env_file()` - Read current .env contents
- `update_env_variable(key, value)` - Update or comment out env variables
- `get_current_auth_method()` - Determine active auth method
- `set_auth_method(method, api_key)` - Switch auth method and update .env
- `get_masked_api_key()` - Return masked key for display

## How To Reapply After Upstream Updates

If you pull new AutoCoder changes and this customization breaks, follow these steps:

### Step 1: Verify Custom Files Exist

```bash
cd ~/projects/autocoder
ls -l custom/auth_config.py
ls -l custom/docs/auth-settings-customization.md
```

If these files are missing, they may have been deleted. Restore from backup or recreate using this documentation.

### Step 2: Apply Backend Changes

#### 2a. Update `server/schemas.py`

Find the `SettingsResponse` class (around line 366) and add these fields:

```python
class SettingsResponse(BaseModel):
    """Response schema for global settings."""
    yolo_mode: bool = False
    model: str = DEFAULT_MODEL
    glm_mode: bool = False  # True if GLM API is configured via .env
    auth_method: Literal["claude_login", "api_key"] = "claude_login"  # CUSTOM
    api_key_configured: bool = False  # CUSTOM
```

Find the `SettingsUpdate` class (around line 379) and add these fields:

```python
class SettingsUpdate(BaseModel):
    """Request schema for updating global settings."""
    yolo_mode: bool | None = None
    model: str | None = None
    auth_method: Literal["claude_login", "api_key"] | None = None  # CUSTOM
    api_key: str | None = None  # CUSTOM
```

#### 2b. Update `server/routers/settings.py`

Add import at the top (after other imports):

```python
# CUSTOM: Import auth configuration utility
from custom.auth_config import get_current_auth_method, set_auth_method
```

Update `get_settings()` function to include auth fields:

```python
@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current global settings."""
    all_settings = get_all_settings()

    # CUSTOM: Get authentication method
    auth_method, api_key_configured = get_current_auth_method()

    return SettingsResponse(
        yolo_mode=_parse_yolo_mode(all_settings.get("yolo_mode")),
        model=all_settings.get("model", DEFAULT_MODEL),
        glm_mode=_is_glm_mode(),
        auth_method=auth_method,
        api_key_configured=api_key_configured,
    )
```

Update `update_settings()` function - add before "Return updated settings":

```python
    # CUSTOM: Handle authentication method changes
    if update.auth_method is not None:
        try:
            if update.auth_method == "api_key":
                if not update.api_key:
                    raise HTTPException(
                        status_code=400,
                        detail="API key is required when switching to API key authentication"
                    )
                set_auth_method("api_key", update.api_key)
            else:
                set_auth_method("claude_login")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif update.api_key is not None:
        try:
            set_auth_method("api_key", update.api_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Update return statement to include auth fields
    auth_method, api_key_configured = get_current_auth_method()

    return SettingsResponse(
        yolo_mode=_parse_yolo_mode(all_settings.get("yolo_mode")),
        model=all_settings.get("model", DEFAULT_MODEL),
        glm_mode=_is_glm_mode(),
        auth_method=auth_method,
        api_key_configured=api_key_configured,
    )
```

#### 2c. Update `server/routers/status.py`

This is the largest change. Add CSS, HTML, and JavaScript for the auth panel.

**CSS:** Add before `</style>` tag (around line 804):

```css
        /* CUSTOM: Auth Settings Panel */
        .auth-settings {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 32px;
        }

        .auth-settings h2 {
            font-size: 18px;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .auth-form {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .form-group label {
            font-size: 14px;
            font-weight: 500;
            color: #374151;
        }

        .radio-group {
            display: flex;
            gap: 24px;
        }

        .radio-option {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }

        .radio-option input[type="radio"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }

        .radio-option label {
            cursor: pointer;
            margin: 0;
        }

        .form-group input[type="password"],
        .form-group input[type="text"] {
            padding: 10px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Monaco', 'Menlo', monospace;
            transition: border-color 0.2s;
        }

        .form-group input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .form-group input:disabled {
            background: #f3f4f6;
            cursor: not-allowed;
        }

        .auth-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .btn {
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .btn-primary {
            background: #3b82f6;
            color: white;
        }

        .btn-primary:hover:not(:disabled) {
            background: #2563eb;
        }

        .btn-primary:disabled {
            background: #9ca3af;
            cursor: not-allowed;
        }

        .auth-status {
            font-size: 13px;
            padding: 8px 12px;
            border-radius: 6px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .auth-status.success {
            background: #d1fae5;
            color: #065f46;
        }

        .auth-status.info {
            background: #dbeafe;
            color: #1e40af;
        }

        .auth-status.error {
            background: #fee2e2;
            color: #991b1b;
        }

        .hint {
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
        }
```

**HTML:** Add after `</header>` tag (around line 811):

```html
        <!-- CUSTOM: Authentication Settings -->
        <div class="auth-settings">
            <h2>🔐 Authentication Settings</h2>
            <div class="auth-form">
                <div class="form-group">
                    <label>Authentication Method</label>
                    <div class="radio-group">
                        <div class="radio-option">
                            <input type="radio" id="auth-claude" name="auth-method" value="claude_login" checked>
                            <label for="auth-claude">Claude Login (claude login)</label>
                        </div>
                        <div class="radio-option">
                            <input type="radio" id="auth-api" name="auth-method" value="api_key">
                            <label for="auth-api">API Key (Anthropic API)</label>
                        </div>
                    </div>
                </div>

                <div class="form-group" id="api-key-group" style="display: none;">
                    <label for="api-key">Anthropic API Key</label>
                    <input type="password" id="api-key" placeholder="sk-ant-api03-...">
                    <div class="hint">Your API key will be saved to .env file. Get one from https://console.anthropic.com/</div>
                </div>

                <div class="auth-actions">
                    <button class="btn btn-primary" id="save-auth">Save Authentication Settings</button>
                    <span class="auth-status" id="auth-status" style="display: none;"></span>
                </div>
            </div>
        </div>
```

**JavaScript:** Add at the beginning of `<script>` tag (around line 1027), right after `let lastDataStr = null;`:

```javascript
        // CUSTOM: Authentication Settings
        // Load current auth settings on page load
        async function loadAuthSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();

                // Set radio button based on current method
                if (data.auth_method === 'api_key') {
                    document.getElementById('auth-api').checked = true;
                    document.getElementById('api-key-group').style.display = 'flex';
                    if (data.api_key_configured) {
                        document.getElementById('api-key').placeholder = '••••••••••••••• (configured)';
                    }
                } else {
                    document.getElementById('auth-claude').checked = true;
                    document.getElementById('api-key-group').style.display = 'none';
                }
            } catch (error) {
                console.error('Failed to load auth settings:', error);
            }
        }

        // Handle auth method radio change
        document.addEventListener('DOMContentLoaded', () => {
            loadAuthSettings();

            // Toggle API key field based on selection
            document.querySelectorAll('input[name="auth-method"]').forEach(radio => {
                radio.addEventListener('change', (e) => {
                    const apiKeyGroup = document.getElementById('api-key-group');
                    if (e.target.value === 'api_key') {
                        apiKeyGroup.style.display = 'flex';
                    } else {
                        apiKeyGroup.style.display = 'none';
                    }
                });
            });

            // Save auth settings
            document.getElementById('save-auth').addEventListener('click', async () => {
                const authMethod = document.querySelector('input[name="auth-method"]:checked').value;
                const apiKey = document.getElementById('api-key').value;
                const statusEl = document.getElementById('auth-status');
                const saveBtn = document.getElementById('save-auth');

                // Validate API key if using API key method
                if (authMethod === 'api_key' && !apiKey) {
                    statusEl.className = 'auth-status error';
                    statusEl.textContent = '❌ API key is required';
                    statusEl.style.display = 'inline-flex';
                    setTimeout(() => statusEl.style.display = 'none', 3000);
                    return;
                }

                // Disable button during save
                saveBtn.disabled = true;
                statusEl.className = 'auth-status info';
                statusEl.textContent = '⏳ Saving...';
                statusEl.style.display = 'inline-flex';

                try {
                    const payload = { auth_method: authMethod };
                    if (authMethod === 'api_key' && apiKey) {
                        payload.api_key = apiKey;
                    }

                    const response = await fetch('/api/settings', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Failed to save settings');
                    }

                    const data = await response.json();

                    // Show success message
                    statusEl.className = 'auth-status success';
                    statusEl.textContent = '✅ Settings saved! Restart agents for changes to take effect.';

                    // Clear API key field if it was set
                    if (authMethod === 'api_key') {
                        document.getElementById('api-key').value = '';
                        document.getElementById('api-key').placeholder = '••••••••••••••• (configured)';
                    }

                    setTimeout(() => statusEl.style.display = 'none', 5000);
                } catch (error) {
                    statusEl.className = 'auth-status error';
                    statusEl.textContent = `❌ ${error.message}`;
                    setTimeout(() => statusEl.style.display = 'none', 5000);
                } finally {
                    saveBtn.disabled = false;
                }
            });
        });
```

### Step 3: Test the Changes

```bash
# Restart the AutoCoder UI
./remote-start.sh stop
./remote-start.sh ui

# Open the status page
# http://localhost:8888/status

# Verify the auth settings panel appears
# Try switching between auth methods
# Ensure settings save correctly
```

### Step 4: Update Custom Index

After successfully reapplying, update `custom/README.md`:

```bash
# Add entry to changelog with today's date
# Update file inventory if line counts changed significantly
# Commit the changes
```

## How It Works

### Backend Flow

1. User selects auth method on `/status` page
2. JavaScript sends PATCH request to `/api/settings`
3. `settings.py` calls `set_auth_method()` from `custom/auth_config.py`
4. `auth_config.py` updates the `.env` file:
   - For API key: Writes `ANTHROPIC_AUTH_TOKEN=sk-ant-...`
   - For Claude login: Comments out `# ANTHROPIC_AUTH_TOKEN=`
5. Settings are returned to confirm the change

### Client.py Integration

The existing `client.py` already handles both auth methods:
- It loads `.env` variables via `dotenv.load_dotenv()`
- It checks for `ANTHROPIC_AUTH_TOKEN` in environment
- If present, the SDK uses the API key
- If absent, the SDK falls back to `claude login` credentials

No changes to `client.py` are needed - it already works!

## Security Considerations

1. **API keys are stored in `.env` file** - This file should have mode 600 (read/write owner only)
2. **Keys are never exposed in API responses** - Only `api_key_configured: true/false` is returned
3. **Keys are masked in UI** - Placeholder shows `••••••••••••••• (configured)`
4. **Input is type="password"** - Keys are hidden while typing

## Troubleshooting

### "Settings don't save"
- Check server logs: `./remote-start.sh logs ui`
- Verify `.env` file permissions: `ls -l .env` (should be `-rw-------`)
- Ensure `custom/auth_config.py` exists

### "Auth method doesn't take effect"
- **Important:** Restart any running agents for changes to apply
- The auth method is loaded when agents start, not dynamically

### "Can't import custom.auth_config"
- Verify Python path includes autocoder root
- Check that `custom/auth_config.py` exists
- Try: `python -c "from custom.auth_config import get_current_auth_method; print('OK')"`

## Future Enhancements

Potential improvements for this feature:
1. Add "Test Connection" button to verify API key works
2. Show estimated API costs based on model selection
3. Add option to rotate API keys
4. Display current API usage/balance
5. Support for multiple API keys (fallback)

## Changelog

### 2026-01-22 - Initial Implementation
- Created `custom/auth_config.py` utility module
- Extended `server/schemas.py` with auth fields
- Modified `server/routers/settings.py` to handle auth changes
- Added auth settings UI panel to `server/routers/status.py`
- Created this documentation file

---

**Last Updated:** 2026-01-22
**Author:** Custom modification for flexible auth switching
**Location:** `custom/docs/auth-settings-customization.md`
