# 2. Literature Review

This section reviews the state of the art across five thematic areas directly relevant to the proposed extended defense framework: LLM jailbreak attacks, RAG system security and poisoning, deployment-level defense techniques, adaptive and multi-turn attack evaluation, and financial AI applications. A total of 20 papers are reviewed and synthesised below. Each sub-section concludes with a direct statement of how the reviewed work informs the proposed methodology.

### 2.1 LLM Jailbreak Attacks
[1] Zou et al. (2023) introduced Greedy Coordinate Gradient (GCG), an optimisation-based white-box attack that automatically appends adversarial suffixes to harmful prompts, achieving near-universal jailbreak success across GPT-3.5, GPT-4, Claude, and LLaMA. GCG established adversarial suffix attacks as a foundational class and demonstrated that RLHF-based alignment is insufficient against gradient-optimised inputs. GCG prompts constitute a significant portion of the JailbreakBench dataset used in both the base paper and the proposed evaluation.

[2] Chao et al. (2023) proposed PAIR (Prompt Automatic Iterative Refinement), a black-box adaptive attack wherein an attacker LLM iteratively refines harmful prompts based on the target model’s rejection responses, achieving high attack success rates in approximately 20 iterations. PAIR is the methodological foundation of Unit 3’s adaptive attack loop in the proposed framework, which tests whether Song & Lee’s (2026) reported 1.67% static ASR holds against a motivated iterative adversary.

[3] Mazeika et al. (2024) presented HarmBench, a standardised evaluation framework for automated red teaming across 18 attack methods and 33 LLMs. A critical finding — that single-turn automated ASRs give reassuringly low values while multi-turn human red teaming exposes failures up to 75% ASR — is the strongest published evidence that static ASR metrics overstate defense effectiveness, directly motivating the adaptive evaluation in Unit 3 and the multi-turn evaluation in Unit 4.

[4] Shen et al. (2024) characterised in-the-wild jailbreak prompts including the DAN (Do Anything Now) family, demonstrating that persona-reassignment attacks remain effective against models lacking explicit anti-persona defenses. The roleplay rewriting strategy in Unit 3’s adaptive attacker directly operationalises DAN-style framing, and the NLI guardrail (Unit 1) must detect facilitating language produced by these prompts in financial contexts.

[5] Chao et al. (2024) introduced JailbreakBench, the open standardised benchmark providing the 300-prompt JBB-Behaviors judge-comparison subset used directly in both the base paper and the proposed project. The benchmark’s explicit design for single-turn evaluation makes it the starting point whose limitations Unit 3 addresses.

Collectively, these works establish the attack landscape against which the proposed framework is evaluated. They justify the choice of JailbreakBench as the evaluation corpus, the need for adaptive attack protocols, and the inclusion of persona-based rewriting as one of three attacker strategies in Unit 3.

### 2.2 RAG System Security and Knowledge Base Threats
[6] Song and Lee (2026) — the base paper — is the direct predecessor of this work. The authors evaluated 32 combinations of three deployment-level defense techniques (safe system prompts, regex filtering, Llama Prompt Guard) against 300 static jailbreak prompts in a financial RAG system, finding that the combination of Safe System Prompt and Input/Output Prompt Guard achieves ASR of 1.67%, FPR of 2.00%, and Defense Efficiency of 0.628. However, the study exclusively targets prompt-layer attacks, does not model retrieval-layer vulnerabilities, evaluates only static non-adaptive attacks, and uses a general-purpose benchmark absent of financial-domain attack categories. These are the four primary gaps addressed by the proposed framework.

[7] Zou et al. (2025) (PoisonedRAG, USENIX Security) demonstrated that injecting as few as five adversarially crafted texts into a RAG knowledge database causes the system to generate attacker-specified responses for targeted queries. Black-box variants require no access to the retriever or LLM. Song & Lee (2026) explicitly exclude knowledge base poisoning from their experimental scope. Unit 2A of the proposed framework directly addresses this exclusion through an embedding centroid anomaly detector that flags out-of-distribution documents at retrieval time.

[8] Xue et al. (2024) (BadRAG) extended knowledge base attacks by targeting the retrieval ranking mechanism, crafting trigger phrases that surface adversarial documents for specific queries without requiring obviously anomalous content. BadRAG motivates the response grounding verifier (Unit 2B): even if a sophisticated poisoned document passes the integrity checker, divergence between response and retrieved context remains detectable via cosine similarity.

[9] Chung (2025) empirically demonstrated that RAG-based LLMs are more vulnerable to jailbreak attacks than non-RAG baselines across 11 foundation models, and that “safe models combined with safe documents can produce unsafe RAG generations” — termed emergent unsafe behaviour. This finding is the primary motivation cited by Song & Lee (2026), and Unit 2B’s response grounding verifier is the first architectural mechanism specifically designed to detect it.

[10] Greshake et al. (2023) formalised indirect prompt injection as a distinct attack class in which adversarial instructions are embedded in externally retrieved content rather than direct user input. This work contextualises both PoisonedRAG and BadRAG within a broader threat taxonomy and motivates why retrieval-layer defense must inspect the semantic content of retrieved documents rather than only filtering user inputs.

These four papers collectively establish the retrieval layer as an under-defended attack surface in financial RAG. The proposed framework’s Unit 2 responds directly to the threats documented in each.

### 2.3 Deployment-Level Defense Techniques
[11] Zhang et al. (2024, ACL) introduced the Goal Prioritization technique, embedding explicit safety-over-helpfulness logic with an [Internal Thoughts] reasoning stage into system prompts. This technique was adopted by Song & Lee (2026) as their best-performing individual defense (ASR reduced from 27.33% to 6.00%). The proposed framework retains this component unchanged as part of the baseline configuration.

[12] Inan et al. (2023) introduced Llama Guard, an LLM-based input-output safeguard fine-tuned on a curated safety taxonomy, demonstrating performance matching or exceeding proprietary moderation APIs. Song & Lee (2026) use Llama Guard 4 12B as the second stage of their ASR evaluation judge. The proposed framework inherits the same judge model for evaluation continuity. Understanding the architectural difference between Llama Guard (LLM-based) and Llama Prompt Guard (BERT-based, 86M) motivates Unit 1’s NLI guardrail, which addresses the context-blindness limitation BERT-based classifiers inherit.

[13] Zheng et al. (2024, ICML) conducted a systematic study of prompt-based safeguarding, finding that safety prompts are brittle against sophisticated multi-step attacks because adversarial pressure can contextually displace safety instructions. This directly motivates the layered architecture retained from Song & Lee (2026): additional filtering layers reduce the attack load that the system prompt must handle alone.

[14] She et al. (2025) examined guardrail robustness specifically in RAG contexts, finding that guardrails trained on standalone single-turn outputs become unreliable when conditioning on retrieved documents. This helps explain the 27.33% baseline ASR in Song & Lee (2026) despite the LLM’s own safety alignment, and motivates the grounding verifier’s retrieval-aware verification over the guardrail’s context-agnostic classification.

These works establish the theoretical and empirical basis for the defense components retained from the base paper and motivate the two new components added by the proposed framework.

### 2.4 Adaptive and Multi-Turn Attack Evaluation
[15] Yang et al. (2024) introduced a systematic analysis of multi-turn jailbreaks exploiting conversation history, demonstrating that decomposing a harmful objective into a sequence of individually borderline sub-queries achieves substantially higher ASR than single-turn variants against goal-prioritisation-defended models. This work directly supports Unit 4’s hypothesis: financial chatbots maintaining session context for coherent advisory conversations are specifically vulnerable to this escalation pattern.

[16] Anonymous (2025) demonstrated Foot-in-the-Door (FITD) multi-turn jailbreaking, showing that small initial compliance increases susceptibility to larger subsequent requests. Experimental results showed FITD increases ASR by up to 51% compared to single-turn approaches. The three-turn sequence structure in Unit 4 directly mirrors FITD: Turn 1 (benign context-building), Turn 2 (boundary-pushing follow-up), Turn 3 (target harmful request framed as a natural continuation).

[17] Asai et al. (2024) introduced SELF-RAG, a framework using cosine similarity between generated responses and retrieved evidence to assess faithfulness, with a critique-generate loop for self-correction. This work provides empirical grounding for Unit 2B’s response grounding verifier: using response-retrieval cosine similarity as a security check has precedent in the RAG faithfulness literature, where response-retrieval divergence has been validated as a reliable indicator of ungrounded generation.

These works justify the two evaluation extensions in the proposed framework and provide the technical precedent for the grounding verifier’s core mechanism.

### 2.5 Financial AI Applications and Safety
[18] Ouyang et al. (2022) introduced RLHF as the dominant model-level safety alignment paradigm. Song & Lee (2026) explicitly exclude RLHF-based defenses from their scope because financial institutions using commercial LLMs cannot access model weights for retraining. The proposed framework maintains this deployment-level scope. Ouyang et al.’s work contextualises why strong parametric alignment is insufficient in RAG contexts, as confirmed by Chung (2025).

[19] Darji et al. (2024) surveyed RAG applications in finance, documenting adversarial query attempts in production financial chatbots across customer service, compliance monitoring, and investment research contexts. Their evidence establishes that jailbreak attempts against financial chatbots are an observed production phenomenon, not merely a theoretical concern, providing empirical motivation for the entire research programme.

[20] Financial Services Commission, Korea (2025) published regulatory guidance mandating safety evaluation and access control for LLM deployments in Korean financial services under the regulatory sandbox programme — the same programme motivating Song & Lee’s (2026) work. This regulatory context establishes the practical necessity of formal defense frameworks and provides the institutional motivation for the fourth DE weighting profile (Regulatory Compliance) introduced in Unit 5 of the proposed framework.

These works situate the proposed research within a real-world deployment context with measurable regulatory stakes, validating the practical relevance of each component in the proposed extended defense architecture.


## References

[1] Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., & Kiela, D. (2021). Retrieval-augmented generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems (NeurIPS 2021).

[2] Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., & Wang, H. (2024). Retrieval-augmented generation for large language models: A survey. arXiv preprint arXiv:2312.10997.
[3] Iaroshev, I., Pillai, R., Vaglietti, L., & Hanne, T. (2024). Evaluating retrieval-augmented generation models for financial report question and answering. Applied Sciences, 14(20), 9318.
[4] Zou, A., Wang, Z., Carlini, N., Nasr, M., Kolter, J. Z., & Fredrikson, M. (2023). Universal and transferable adversarial attacks on aligned language models. arXiv preprint arXiv:2307.15043.
[5] Chao, P., Debenedetti, E., Robey, A., Andriushchenko, M., Croce, F., Sehwag, V., & Wong, E. (2024). JailbreakBench: An open robustness benchmark for jailbreaking large language models. Neural Information Processing Systems (NeurIPS 2024).
[6] Mazeika, M., Phan, L., Yin, X., Zou, A., Wang, Z., Mu, N., & Hendrycks, D. (2024). HarmBench: A standardised evaluation framework for automated red teaming and robust refusal. Proceedings of Machine Learning Research (ICML 2024), 235, 35181–35224.
[7] Chao, P., Robey, A., Dobriban, E., Hassani, H., Pappas, G. J., & Wong, E. (2023). Jailbreaking black box large language models in twenty queries. arXiv preprint arXiv:2310.08419.
[8] Shen, X., Chen, Z., Backes, M., Shen, Y., & Zhang, Y. (2024). "Do anything now": Characterising and evaluating in-the-wild jailbreak prompts on large language models. CCS '24: The ACM Conference on Computer and Communications Security.
[9] Inan, H., Upasani, K., Chi, J., Rungta, R., Iyer, K., Mao, Y., & Khabsa, M. (2023). Llama Guard: LLM-based input-output safeguard for human-AI conversations. arXiv preprint arXiv:2312.06674.
[10] Zhang, Z., Yang, J., Ke, P., Mi, F., Wang, H., & Huang, M. (2024). Defending large language models against jailbreaking attacks through goal prioritization. Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL 2024).
[11] Zheng, C., Yin, F., Zhou, H., Meng, F., Zhou, J., Chang, K.-W., & Peng, N. (2024). On prompt-driven safeguarding for large language models. International Conference on Machine Learning (ICML 2024).
[12] She, Y., Peterson, D. W., Liu, M. M., Upadhyay, V., Chaghazardi, M. H., Kang, E., & Roth, D. (2025). RAG makes guardrails unsafe? Investigating robustness of guardrails under RAG-style contexts. arXiv preprint arXiv:2510.05310.
[13] Zou, W., Geng, R., Wang, B., & Jia, J. (2025). PoisonedRAG: Knowledge corruption attacks to retrieval-augmented generation of large language models. 34th USENIX Security Symposium (USENIX Security 2025), 3827–3844.
[14] Xue, J., Zheng, M., Hu, Y., Liu, F., Chen, X., & Lou, Q. (2024). BadRAG: Identifying vulnerabilities in retrieval augmented generation of large language models. arXiv preprint arXiv:2406.00083.
[15] Chung, G. (2025). Qualitative imbalance in quantitative growth: An empirical time series analysis of Korea's open banking platform. Platforms, 3(2), 10.
[16] Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injections. Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security (AISec 2023).
[17] Yang, Z., Wei, H., Zhao, X., Zhang, T., & Li, J. (2024). Multi-turn context jailbreak attack on large language models from first principles. arXiv preprint arXiv:2408.04686.
[18] Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C. L., Mishkin, P., & Lowe, R. (2022). Training language models to follow instructions with human feedback. Advances in Neural Information Processing Systems (NeurIPS 2022).
[19] Bai, Y., Kadavath, S., Kundu, S., Askell, A., Kernion, J., Jones, A., & McKinnon, C. (2022). Constitutional AI: Harmlessness from AI feedback. arXiv preprint arXiv:2212.08073.
[20] Rafailov, R., Sharma, A., Mitchell, E., Manning, C. D., Ermon, S., & Finn, C. (2023). Direct preference optimization: Your language model is secretly a reward model. Advances in Neural Information Processing Systems (NeurIPS 2023), 36, 53728–53741.
[21] Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2024). Self-RAG: Learning to retrieve, generate, and critique through self-reflection. International Conference on Learning Representations (ICLR 2024).
[22] Song, E., & Lee, H. (2026). Defending financial RAG systems against jailbreak attacks. Expert Systems with Applications, 317, 131945.