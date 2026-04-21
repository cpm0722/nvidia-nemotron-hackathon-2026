import { callStdin } from '../../../_lib/ari_cli.mjs';

export default {
  name: 'enrich_bodies',
  description: 'EvidenceItem 배열의 body_full을 trafilatura로 채운다.',
  async execute({ evidence, workers } = {}) {
    if (!Array.isArray(evidence)) {
      throw new Error('enrich_bodies: evidence (array) 필수');
    }
    return callStdin('enrich_bodies', { evidence }, { workers });
  },
};
