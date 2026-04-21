import { callStdin } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'synthesize_report',
  description: 'claims + evidence를 받아 Nemotron-3-Super로 한국어 cited 마크다운 리포트 생성.',
  async execute({ claims, evidence, model_name, top_n, max_tokens } = {}) {
    if (!Array.isArray(evidence) || evidence.length === 0) {
      throw new Error('synthesize_report: evidence (non-empty array) 필수');
    }
    return callStdin(
      'synthesize_report',
      { claims: claims || [], evidence, model_name: model_name || '' },
      { top_n, max_tokens, model_name }
    );
  },
};
