import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_reddit',
  description: '지정 서브레딧에서 query 매칭 스레드 수집 (.json fallback).',
  async execute({ query, subreddits, limit, since_days } = {}) {
    if (!query) throw new Error('scrape_reddit: query 필수');
    return callFlag('scrape_reddit', { query, subreddits, limit, since_days });
  },
};
