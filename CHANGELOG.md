# Changelog

## 0.1.0 — 2026-10-12

- Publish the `pro6000-fp16-v1` profile for pinned Strata 0.1.43 and SC117 IQ3_S.
- Add portable config generation, hardware/source checks and Linux process supervision.
- Publish 449 historical engine measurement records with numerical controls, regressions and provenance.
- Add a portable reproduction of the 70-record validation sequence, result comparison and model/logit verification tools.
- Publish English/Chinese documentation and an interactive benchmark page.

The recorded advantage is 32K conversation resumption on the tested PRO 6000 configuration. Decode throughput is essentially unchanged. This release introduces no CUDA-kernel changes or additional precision reduction, and has not completed a multi-day standalone soak test.
