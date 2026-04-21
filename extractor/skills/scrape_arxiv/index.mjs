import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'scrape_arxiv',
  description: 'arXiv에서 query에 매칭되는 최근 논문을 수집한다.',
  async execute({ query, limit, since_days } = {}) {
    if (!query) throw new Error('scrape_arxiv: query 필수');
    return callFlag('scrape_arxiv', { query, limit, since_days });
  },
};
