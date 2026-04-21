import { getBenchmarks } from '../../../_lib/benchmark_api.mjs';

export default {
  name: 'get_benchmarks',
  description: 'LLM Benchmark API에서 모델 벤치마크 점수를 조회한다.',
  async execute({ provider, model, benchmark } = {}) {
    return getBenchmarks({ provider, model, benchmark });
  },
};
