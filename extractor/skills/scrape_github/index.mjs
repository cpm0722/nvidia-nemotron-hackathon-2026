import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_github',
  description: 'GitHub Issues/PR/Releases 검색으로 query 관련 항목 수집.',
  async execute({ query, repo, limit, since_days } = {}) {
    if (!query) throw new Error('scrape_github: query 필수');
    return callFlag('scrape_github', { query, repo, limit, since_days });
  },
};
