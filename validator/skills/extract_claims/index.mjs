import { callFlag } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'extract_claims',
  description: '공식 릴리스 URL에서 검증 가능한 claim 목록을 LLM으로 추출한다.',
  async execute({ url, max_input_chars } = {}) {
    if (!url) throw new Error('extract_claims: url 필수');
    return callFlag('extract_claims', { url, max_input_chars });
  },
};
