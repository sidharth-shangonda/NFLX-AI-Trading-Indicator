# HistGradientBoosting early stopping

- Source URL: https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html
- Retrieval date: 2026-11-03.
- Library/documentation version: scikit-learn 1.9.1.
- Note: With `early_stopping="auto"`, the pinned classifier enables early stopping above 10,000 training samples. The installed 1.9.1 source uses `train_test_split` to create validation data in that case, so this project must set `early_stopping=False` to preserve chronological validation.
