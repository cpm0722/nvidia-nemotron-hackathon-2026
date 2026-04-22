### TL;DR
- 2026 엔비디아 Nemotron Hackathon의 Track A "Creative Agentic Systems" 프로젝트
- 새로 나온 AI 프러덕트 (모델, API, 솔루션, 프레임워크, Feature 등)에 대한 오피셜한 성능(벤치마크 등)과 실사용자 반응 및 피드백을 모아서 요약/정리하는 에이전트
- Agent Framework: NemoClaw(OpenClaw + NVIDIA의 보안 솔루션) 기반
- Backbone Model: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard), [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- GPU Resource: H100 4GPU


### Architecture
- Extractor: 다양한 출처에서 정보를 수집하는 Agent
  - 정보 출처
    - Official Blog
    - Benchmark site
    - arxiv.org (paper)
    - Reddit
    - GitHub Issue
    - HuggingFace

- Validator: 수집한 정보를 검증/필터링하는 Agent
