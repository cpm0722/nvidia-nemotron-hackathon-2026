import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_hf_papers',
  description: 'HuggingFace Papers에서 query 관련 논문 수집.',
  async execute({ query, limit, since_days } = {}) {
    if (!query) throw new Error('scrape_hf_papers: query 필수');
    return callFlag('scrape_hf_papers', { query, limit, since_days });
  },
};
