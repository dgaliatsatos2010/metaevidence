# MetaEvidence v1.0.0

MetaEvidence v1.0.0 is the first stable public release after completion of the locked external-validation programme.

## Frozen method
The publication-deduplication engine remains byte-identical to the method frozen before external outcome inspection.

`src/metaevidence/dedup.py`

SHA-256: `3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`

No feature, weight, threshold, blocking rule, retention rule or held-out gold-label interpretation was changed in response to validation outcomes.

## Primary protected ASySD held-out validation
- Depression: N=79,880; sensitivity 0.7007; specificity 0.9602; precision 0.7192; F1 0.7098.
- SRSR: N=53,001; sensitivity 0.8590; specificity 0.9333; precision 0.8572; F1 0.8581.
- Pooled micro, N=132,881: sensitivity 0.7996; specificity 0.9510; precision 0.8063; F1 0.8029; accuracy 0.9203.
- Confusion matrix: TP=21,581; TN=100,706; FP=5,185; FN=5,409.

Successful run: GitHub Actions `34148618804`, commit `a89033dfe716ff7beae2465bdb8852d82dee35fc`.

## Independent five-corpus EndNote validation
Across 9,835 records: sensitivity 0.6293; specificity 0.9732; precision 0.9559; F1 0.7589.

Successful run: GitHub Actions `34114902004`, commit `4198fee893744d73da9e5fbf57e6da87877c0b8a`.

## Reproducibility
Results-only validation evidence is included in `validation_evidence/`. Raw third-party benchmark files are not redistributed.

## Software verification
151/151 automated tests passed during v1.0.0 release preparation.
