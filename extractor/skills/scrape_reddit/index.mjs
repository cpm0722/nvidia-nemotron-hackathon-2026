import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_reddit',
  description:
    '지정 서브레딧에서 query 매칭 스레드 수집 (.json fallback). 클라우드 IP(Brev 등)가 Reddit 403이면 cache_file로 사전 수집 JSON 로드.',
  async execute({ query, subreddits, limit, since_days, cache_file } = {}) {
    if (!cache_file && !query) {
      throw new Error(
        'scrape_reddit: query 필수 (또는 cache_file로 docs/cache/reddit-*.json 지정)'
      );
    }
    return callFlag('scrape_reddit', {
      query,
      subreddits,
      limit,
      since_days,
      cache_file,
    });
  },
};
