"""Run in the sklearn-1.4 env: export Person 2's pipeline to portable JSON."""
import json, joblib, numpy as np, sys
m = joblib.load(sys.argv[1])
ct, clf = m.named_steps["preprocessor"], m.named_steps["classifier"]
num = ct.transformers_[0][2]; cat_cols = ct.transformers_[1][2]
enc = ct.named_transformers_["cat"]
trees = []
for it in clf._predictors:
    p = it[0]; n = p.nodes
    trees.append({k: n[k].tolist() for k in ["value", "feature_idx", "num_threshold", "missing_go_to_left", "left", "right", "is_leaf"]})
out = {"format": "journalguard-hgb-v1", "sklearn_version_trained": "1.4.0",
       "numeric_features": list(num), "categorical_features": list(cat_cols),
       "categories": [list(map(str, c)) for c in enc.categories_],
       "baseline": float(np.ravel(clf._baseline_prediction)[0]), "trees": trees,
       "params": {"learning_rate": clf.learning_rate, "max_iter": clf.max_iter, "max_depth": clf.max_depth}}
json.dump(out, open(sys.argv[2], "w"))
print("trees", len(trees), "features", len(num) + sum(len(c) for c in enc.categories_))
