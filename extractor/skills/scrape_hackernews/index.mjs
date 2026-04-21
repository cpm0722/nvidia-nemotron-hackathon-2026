import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_hackernews',
  description: 'HN Algolia 검색으로 query 관련 스토리 수집.',
  async execute({ query, limit, since_days } = {}) {
    if (!query) throw new Error('scrape_hackernews: query 필수');
    return callFlag('scrape_hackernews', { query, limit, since_days });
  },
};
