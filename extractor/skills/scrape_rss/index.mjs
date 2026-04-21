import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_rss',
  description: '사전 등록된 키 또는 임의 URL의 RSS/Atom 피드 최신 글을 수집한다.',
  async execute({ feed_key, feed_url, query, limit } = {}) {
    if (!feed_key && !feed_url) {
      throw new Error('scrape_rss: feed_key 또는 feed_url 중 하나는 반드시 필요합니다');
    }
    return callFlag('scrape_rss', { feed_key, feed_url, query, limit });
  },
};
