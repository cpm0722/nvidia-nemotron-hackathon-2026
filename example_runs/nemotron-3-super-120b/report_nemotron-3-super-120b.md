# Nemotron 3 Super 120B

## Executive Summary
NVIDIA Nemotron 3 Super 120B is a 120‑billion‑parameter mixture‑of‑experts language model with 12 billion active parameters, built on a LatentMoE architecture that blends Mamba‑2, MoE, and attention layers and includes Multi‑Token Prediction for faster generation【1】【2】. The model supports up to 1 million token context, is released under the NVIDIA Nemotron Open Model License, and targets agentic workflows, long‑context reasoning, and high‑volume workloads such as IT ticket automation【2】. Official benchmark results show strong performance on reasoning and coding tasks, including an 83.73 % MMLU‑Pro score and a 90.21 % AIME25 (no tools) score【2】. Community discussion was not captured in the collected evidence, so the assessment relies primarily on vendor‑provided data. Overall, the model appears competitive in reasoning and agentic benchmarks, though real‑world deployment would benefit from independent validation.

## Official Performance
The Nemotron 3 Super 120B achieves an Intelligence Index of 35.97, a Coding Index of 31.19, and an Agentic Index of 40.18 on the Artificial Analysis benchmark suite【1】. On the same suite it scores 80.0 % on GPQA Diamond, 19.2 % on HLE, 36.0 % on SciCode, 67.8 % on TAU‑2, 71.5 % on IFBench, and 60.0 % on LCR【1】. According to the HuggingFace model card, the model requires a minimum of 8× H100‑80GB GPUs and attains 83.73 % on MMLU‑Pro, 90.21 % on AIME25 (no tools), and 93.67 % on HMMT Feb25 (no tools)【2】. Additional strengths include 94.73 % on HMMT Feb25 with tools, 82.70 % on GPQA with tools, 81.19 % on LiveCodeBench, and 42.05 % on SciCode (subtask)【2】. Long‑context evaluations show RULER scores of 96.30 % at 256k tokens, 95.67 % at 512k tokens, and 91.75 % at 1M tokens, indicating robust retention over extended inputs【2】. These figures position the model favorably against peers such as Qwen3.5‑122B and GPT‑OSS‑120B on several reasoning and agentic metrics【2】.

## Community Reactions
No substantive community discussion was captured in the collected evidence.

## Key Takeaways
- Verify the model’s reasoning and agentic capabilities on your own benchmarks before committing to production workloads.  
- Ensure you have access to at least eight H100‑80GB GPUs to meet the minimum hardware requirement for efficient inference.  
- Leverage the configurable reasoning flag (`enable_thinking`) to trade off latency and depth of thought for specific use cases.  
- Consider the model’s permissive NVIDIA Nemotron Open Model License when planning commercial deployment or redistribution.  
- Utilize the provided multi‑language support (English, French, German, Italian, Japanese, Spanish, Chinese) for multilingual applications.  
- Monitor updates from NVIDIA’s Nemotron developer repository for future improvements and community‑contributed tooling.  
- Evaluate the model’s long‑context performance if your application requires processing documents exceeding 256k tokens.
