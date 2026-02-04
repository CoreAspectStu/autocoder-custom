/**
 * GettingStarted Documentation Section
 *
 * Covers what AutoForge is, quick start commands,
 * creating and adding projects, and system requirements.
 */

import { Badge } from '@/components/ui/badge'

/** CLI command descriptor for the reference table. */
interface CliCommand {
  command: string
  description: string
}

const CLI_COMMANDS: CliCommand[] = [
  { command: 'autoforge', description: 'Start the server (default)' },
  { command: 'autoforge config', description: 'Open ~/.autoforge/.env in your editor' },
  { command: 'autoforge config --path', description: 'Print config file path' },
  { command: 'autoforge config --show', description: 'Show active configuration values' },
  { command: 'autoforge --port PORT', description: 'Custom port (default: auto from 8888)' },
  { command: 'autoforge --host HOST', description: 'Custom host (default: 127.0.0.1)' },
  { command: 'autoforge --no-browser', description: "Don't auto-open browser" },
  { command: 'autoforge --repair', description: 'Delete and recreate virtual environment' },
  { command: 'autoforge --version', description: 'Print version' },
  { command: 'autoforge --help', description: 'Show help' },
]

export function GettingStarted() {
  return (
    <div>
      {/* What is AutoForge? */}
      <h3 id="what-is-autoforge" className="text-lg font-semibold text-foreground mt-8 mb-3">
        What is AutoForge?
      </h3>
      <p className="text-muted-foreground mb-4">
        AutoForge is an autonomous coding agent system that builds complete applications over multiple
        sessions using a two-agent pattern:
      </p>
      <ol className="list-decimal space-y-2 ml-4 text-muted-foreground">
        <li>
          <strong className="text-foreground">Initializer Agent</strong> &mdash; reads your app spec
          and creates features in a SQLite database
        </li>
        <li>
          <strong className="text-foreground">Coding Agent</strong> &mdash; implements features one by
          one, marking each as passing when complete
        </li>
      </ol>
      <p className="text-muted-foreground mt-4">
        It comes with a React-based UI for monitoring progress, managing features, and controlling agents
        in real time.
      </p>

      {/* Installation */}
      <h3 id="installation" className="text-lg font-semibold text-foreground mt-8 mb-3">
        Installation
      </h3>
      <p className="text-muted-foreground mb-3">
        Install AutoForge globally via npm:
      </p>
      <div className="bg-muted rounded-lg p-4 font-mono text-sm">
        <pre><code>{`npm install -g autoforge-ai`}</code></pre>
      </div>
      <p className="text-muted-foreground mt-3">
        This requires{' '}
        <strong className="text-foreground">Node.js 20+</strong> and{' '}
        <strong className="text-foreground">Python 3.11+</strong>.
        Python is auto-detected on first run.
      </p>

      {/* Quick Start */}
      <h3 id="quick-start" className="text-lg font-semibold text-foreground mt-8 mb-3">
        Quick Start
      </h3>
      <p className="text-muted-foreground mb-3">
        After installing, start AutoForge with a single command:
      </p>
      <div className="bg-muted rounded-lg p-4 font-mono text-sm">
        <pre><code>{`autoforge`}</code></pre>
      </div>
      <p className="text-muted-foreground mt-3 mb-2">
        On first run, AutoForge automatically:
      </p>
      <ol className="list-decimal space-y-1 ml-4 text-muted-foreground">
        <li>Checks for Python 3.11+</li>
        <li>Creates a virtual environment at{' '}
          <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">~/.autoforge/venv/</span>
        </li>
        <li>Installs Python dependencies</li>
        <li>Copies a default config file to{' '}
          <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">~/.autoforge/.env</span>
        </li>
        <li>Starts the server and opens your browser</li>
      </ol>
      <p className="text-muted-foreground mt-3">
        On subsequent runs, AutoForge starts instantly &mdash; the environment is already set up.
      </p>

      <h4 className="text-base font-semibold text-foreground mt-6 mb-3">
        Running from Source
      </h4>
      <p className="text-muted-foreground mb-3">
        If you prefer to clone the repository (for development or contributing):
      </p>
      <div className="bg-muted rounded-lg p-4 font-mono text-sm">
        <pre><code>{`# Windows
start_ui.bat       # Web UI

# macOS/Linux
./start_ui.sh      # Web UI`}</code></pre>
      </div>

      {/* CLI Commands */}
      <h3 id="cli-commands" className="text-lg font-semibold text-foreground mt-8 mb-3">
        CLI Commands
      </h3>
      <p className="text-muted-foreground mb-3">
        The{' '}
        <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">autoforge</span>{' '}
        command supports these options:
      </p>
      <table className="w-full text-sm mt-3">
        <thead>
          <tr className="bg-muted/50">
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Command
            </th>
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Description
            </th>
          </tr>
        </thead>
        <tbody className="text-muted-foreground">
          {CLI_COMMANDS.map((c) => (
            <tr key={c.command}>
              <td className="border border-border px-3 py-2">
                <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">{c.command}</span>
              </td>
              <td className="border border-border px-3 py-2">{c.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4 className="text-base font-semibold text-foreground mt-6 mb-3">
        Configuration
      </h4>
      <p className="text-muted-foreground mb-3">
        AutoForge reads configuration from a{' '}
        <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">.env</span>{' '}
        file. The location depends on your install method:
      </p>
      <table className="w-full text-sm mt-3">
        <thead>
          <tr className="bg-muted/50">
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Install method
            </th>
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Config location
            </th>
          </tr>
        </thead>
        <tbody className="text-muted-foreground">
          <tr>
            <td className="border border-border px-3 py-2">npm (global)</td>
            <td className="border border-border px-3 py-2">
              <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">~/.autoforge/.env</span>
            </td>
          </tr>
          <tr>
            <td className="border border-border px-3 py-2">From source</td>
            <td className="border border-border px-3 py-2">
              <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">.env</span>{' '}
              in the project root
            </td>
          </tr>
        </tbody>
      </table>
      <p className="text-muted-foreground mt-3">
        Run{' '}
        <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">autoforge config</span>{' '}
        to open the config file in your editor, or{' '}
        <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">autoforge config --show</span>{' '}
        to print the active values. See{' '}
        <a href="#/docs/advanced-config" className="text-primary underline">Advanced Configuration</a>{' '}
        for API provider setup (Ollama, Vertex AI, z.ai).
      </p>

      {/* Creating a New Project */}
      <h3 id="creating-a-project" className="text-lg font-semibold text-foreground mt-8 mb-3">
        Creating a New Project
      </h3>
      <ul className="list-disc space-y-2 ml-4 text-muted-foreground">
        <li>
          From the UI, click the project dropdown and select{' '}
          <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">Create New Project</span>
        </li>
        <li>Enter a name and select or browse to a folder for the project</li>
        <li>
          Create an app spec interactively with Claude, or write one manually in XML format
        </li>
        <li>
          The initializer agent reads your spec and creates features automatically
        </li>
      </ul>

      {/* Adding to an Existing Project */}
      <h3 id="existing-project" className="text-lg font-semibold text-foreground mt-8 mb-3">
        Adding to an Existing Project
      </h3>
      <ul className="list-disc space-y-2 ml-4 text-muted-foreground">
        <li>Register the project folder via the UI project selector</li>
        <li>
          AutoForge creates a{' '}
          <span className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">.autoforge/</span>{' '}
          directory inside your project
        </li>
        <li>
          Existing code is preserved &mdash; AutoForge adds its configuration alongside it
        </li>
        <li>Write or generate an app spec describing what to build</li>
      </ul>

      {/* System Requirements */}
      <h3 id="system-requirements" className="text-lg font-semibold text-foreground mt-8 mb-3">
        System Requirements
      </h3>
      <table className="w-full text-sm mt-3">
        <thead>
          <tr className="bg-muted/50">
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Requirement
            </th>
            <th className="border border-border px-3 py-2 text-left font-medium text-foreground">
              Details
            </th>
          </tr>
        </thead>
        <tbody className="text-muted-foreground">
          <tr>
            <td className="border border-border px-3 py-2">Node.js</td>
            <td className="border border-border px-3 py-2">
              <Badge variant="secondary">20+</Badge>{' '}
              <span className="text-xs">(required for CLI and UI)</span>
            </td>
          </tr>
          <tr>
            <td className="border border-border px-3 py-2">Python</td>
            <td className="border border-border px-3 py-2">
              <Badge variant="secondary">3.11+</Badge>{' '}
              <span className="text-xs">(auto-detected on first run)</span>
            </td>
          </tr>
          <tr>
            <td className="border border-border px-3 py-2">Claude Code CLI</td>
            <td className="border border-border px-3 py-2">
              Required for running agents
            </td>
          </tr>
          <tr>
            <td className="border border-border px-3 py-2">Operating System</td>
            <td className="border border-border px-3 py-2">
              Windows, macOS, or Linux
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
