"""
Monkey-patches for MAPIE v1.2.0 + sklearn 1.8.0 compatibility.

sklearn 1.8.0 requires __sklearn_tags__ method on estimators.
MAPIE's internal EnsembleClassifier/EnsembleRegressor lack this.

Apply once at module import via apply_mapie_patches().
"""

import warnings


def apply_mapie_patches():
    """
    Apply compatibility patches for MAPIE with sklearn 1.8.0.

    Must be called before using any MAPIE classes.
    Safe to call multiple times.
    """
    try:
        from sklearn.utils._tags import (
            ClassifierTags,
            InputTags,
            RegressorTags,
            Tags,
            TargetTags,
        )
    except ImportError:
        warnings.warn(
            "sklearn.utils._tags not available. Patches not needed for sklearn < 1.8.0",
            stacklevel=2,
        )
        return

    # Classifier patch
    def _sklearn_tags_classifier(self):
        return Tags(
            estimator_type="classifier",
            target_tags=TargetTags(required=True, one_d_labels=True),
            input_tags=InputTags(allow_nan=True, two_d_array=True),
            classifier_tags=ClassifierTags(poor_score=False, multi_label=False),
        )

    # Regressor patch
    def _sklearn_tags_regressor(self):
        return Tags(
            estimator_type="regressor",
            target_tags=TargetTags(required=True, one_d_labels=True),
            input_tags=InputTags(allow_nan=True, two_d_array=True),
            regressor_tags=RegressorTags(poor_score=False),
        )

    try:
        from mapie.estimator.classifier import EnsembleClassifier

        if not hasattr(EnsembleClassifier, "__sklearn_tags__"):
            EnsembleClassifier.__sklearn_tags__ = _sklearn_tags_classifier
    except ImportError:
        pass

    try:
        from mapie.estimator.regressor import EnsembleRegressor

        if not hasattr(EnsembleRegressor, "__sklearn_tags__"):
            EnsembleRegressor.__sklearn_tags__ = _sklearn_tags_regressor
    except ImportError:
        pass

    # Patch our custom ModelEnsemble for sklearn 1.8.0 compatibility
    try:
        from scripts.target_models.models.ensemble import ModelEnsemble

        if not hasattr(ModelEnsemble, "__sklearn_tags__"):
            # ModelEnsemble can be either classifier or regressor depending on config
            # Use a dynamic approach based on config.is_classification
            def _model_ensemble_sklearn_tags(self):
                if self.config.is_classification:
                    return Tags(
                        estimator_type="classifier",
                        target_tags=TargetTags(required=True, one_d_labels=True),
                        input_tags=InputTags(allow_nan=True, two_d_array=True),
                        classifier_tags=ClassifierTags(
                            poor_score=False, multi_label=False
                        ),
                    )
                else:
                    return Tags(
                        estimator_type="regressor",
                        target_tags=TargetTags(required=True, one_d_labels=True),
                        input_tags=InputTags(allow_nan=True, two_d_array=True),
                        regressor_tags=RegressorTags(poor_score=False),
                    )

            ModelEnsemble.__sklearn_tags__ = _model_ensemble_sklearn_tags
    except ImportError:
        pass
