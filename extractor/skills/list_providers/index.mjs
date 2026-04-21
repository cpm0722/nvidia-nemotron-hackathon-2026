import { listProviders } from '../../../_lib/benchmark_api.mjs';

export default {
  name: 'list_providers',
  description: 'LLM Benchmark API에 수집된 AI 제공사 목록을 반환한다.',
  async execute() {
    return listProviders();
  },
};
