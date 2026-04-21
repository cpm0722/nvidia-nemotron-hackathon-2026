import { getStatus } from '../../../_lib/benchmark_api.mjs';

export default {
  name: 'get_status',
  description: 'LLM Benchmark API의 소스별 마지막 수집 상태를 반환한다.',
  async execute() {
    return getStatus();
  },
};
