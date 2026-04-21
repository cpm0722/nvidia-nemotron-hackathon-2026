import { triggerFetch } from '../../../_lib/benchmark_api.mjs';

export default {
  name: 'trigger_fetch',
  description: 'LLM Benchmark API에 모든 소스 즉시 수집을 요청한다.',
  async execute() {
    return triggerFetch();
  },
};
