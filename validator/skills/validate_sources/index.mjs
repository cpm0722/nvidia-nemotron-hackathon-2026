import { callStdin } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'validate_sources',
  description: 'EvidenceItem 배열에 룰 기반 2축 점수 매김 (authority, verifiability).',
  async execute({ evidence } = {}) {
    if (!Array.isArray(evidence)) {
      throw new Error('validate_sources: evidence (array) 필수');
    }
    return callStdin('validate_sources', { evidence });
  },
};
