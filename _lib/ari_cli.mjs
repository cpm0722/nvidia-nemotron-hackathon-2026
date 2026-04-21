// Shared helper for all ari_agent-backed OpenClaw skills.
//
// Each skill spawns `python -m ari_agent.cli <subcommand> ...` and parses JSON
// from stdout. Two transport modes:
//   - flag: args passed as --flag value (scrapers + extract_claims)
//   - stdin: args piped as JSON via stdin (enrich_bodies, validate_sources, synthesize_report)
//
// Env:
//   ARI_AGENT_HOME        — cwd for subprocess (defaults to OPENCLAW_WORKSPACE_DIR or cwd)
//   ARI_PYTHON            — python interpreter (default: `python`)
//   ARI_LLM_PROVIDER      — brev | build | local-nim (forwarded to CLI)
//   NEMOTRON_BASE_URL     — override provider base URL
//   NVIDIA_API_KEY        — required for build provider

import { spawn } from 'node:child_process';

const DEFAULT_PYTHON = process.env.ARI_PYTHON || 'python';

function resolveCwd() {
  return (
    process.env.ARI_AGENT_HOME ||
    process.env.OPENCLAW_WORKSPACE_DIR ||
    process.cwd()
  );
}

function buildArgs(subcommand, flagMap) {
  const args = ['-m', 'ari_agent.cli', subcommand];
  for (const [flag, value] of Object.entries(flagMap || {})) {
    if (value === undefined || value === null || value === '') continue;
    args.push(`--${flag.replace(/_/g, '-')}`, String(value));
  }
  return args;
}

async function run(args, { stdinPayload } = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn(DEFAULT_PYTHON, args, {
      cwd: resolveCwd(),
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => (stdout += d.toString('utf8')));
    proc.stderr.on('data', (d) => (stderr += d.toString('utf8')));
    proc.on('error', (err) => reject(err));
    proc.on('close', (code) => {
      if (code !== 0) {
        return reject(
          new Error(
            `ari_agent.cli exited ${code}: ${stderr.trim() || '(no stderr)'}`
          )
        );
      }
      const trimmed = stdout.trim();
      if (!trimmed) return reject(new Error('ari_agent.cli produced empty stdout'));
      try {
        resolve(JSON.parse(trimmed));
      } catch (e) {
        reject(new Error(`ari_agent.cli stdout not JSON: ${trimmed.slice(0, 400)}`));
      }
    });
    if (stdinPayload !== undefined) {
      proc.stdin.write(JSON.stringify(stdinPayload));
      proc.stdin.end();
    } else {
      proc.stdin.end();
    }
  });
}

export async function callFlag(subcommand, flagMap = {}) {
  return run(buildArgs(subcommand, flagMap));
}

export async function callStdin(subcommand, payload, flagMap = {}) {
  return run(buildArgs(subcommand, flagMap), { stdinPayload: payload });
}
