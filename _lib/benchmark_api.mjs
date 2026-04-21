// HTTP client for LLM Benchmark API.
//
// Env:
//   BENCHMARK_API_URL  — base URL of the running FastAPI server (default: http://localhost:8000)

const BASE_URL = (process.env.BENCHMARK_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) throw new Error(`benchmark-api HTTP ${res.status} on ${path}`);
  return res.json();
}

export async function getBenchmarks({ provider, model, benchmark } = {}) {
  const params = new URLSearchParams();
  if (provider) params.set('provider', provider);
  if (model) params.set('model', model);
  if (benchmark) params.set('benchmark', benchmark);
  const qs = params.toString();
  const items = await apiFetch(`/benchmarks${qs ? `?${qs}` : ''}`);
  return {
    total: items.length,
    showing: items.length,
    results: items,
  };
}

export async function listProviders() {
  return apiFetch('/providers');
}

export async function getStatus() {
  return apiFetch('/status');
}

export async function triggerFetch() {
  return apiFetch('/fetch', { method: 'POST' });
}
