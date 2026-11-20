"""Integrated Gradients 與 KerasModelRunner（design.md 3.3：完整性、解析解、確定性）。"""

from typing import Any

import numpy as np
import pytest

from churn_api.inference.explainer import IntegratedGradientsExplainer
from churn_api.inference.model_runner import KerasModelRunner

N = 12  # 測試用小維度


def _mlp(seed: int = 0) -> Any:
    import keras

    keras.utils.set_random_seed(seed)
    return keras.Sequential(
        [
            keras.Input(shape=(N,)),
            keras.layers.Dense(8, activation="relu"),
            keras.layers.Dense(1, activation="sigmoid"),
        ]
    )


def _linear(weights: np.ndarray[Any, Any], bias: float) -> Any:
    import keras

    model = keras.Sequential([keras.Input(shape=(N,)), keras.layers.Dense(1, activation="sigmoid")])
    model.layers[0].set_weights(
        [weights.reshape(N, 1).astype("float32"), np.array([bias], "float32")]
    )
    return model


def _rng_vectors(count: int, seed: int = 1) -> np.ndarray[Any, Any]:
    return np.random.default_rng(seed).normal(size=(count, N)).astype(np.float32)


def test_completeness_sum_equals_probability_difference() -> None:
    """|Σ impact − (p(x) − p(基準))| < 0.01（design.md 3.3 正確性驗證 ①）。"""
    model = _mlp()
    baseline = _rng_vectors(1, seed=7)[0]
    explainer = IntegratedGradientsExplainer(model, baseline, 0.5, steps=64)
    runner = KerasModelRunner(model)
    for x in _rng_vectors(8):
        attribution, p_base, p_x = explainer.attribute_with_endpoints(x)
        assert attribution.shape == (N,)
        assert abs(attribution.sum() - (p_x - p_base)) < 0.01
        assert p_x == pytest.approx(runner.predict_proba(x[None, :])[0], abs=1e-6)
        assert p_base == pytest.approx(runner.predict_proba(baseline[None, :])[0], abs=1e-6)


def test_linear_model_in_logit_space_equals_analytic_solution() -> None:
    """無隱藏層 sigmoid 模型在 logit 空間：IG_i = w_i·(x_i − b_i)（design.md 3.3 ②）。"""
    weights = np.linspace(-1.5, 2.0, N)
    model = _linear(weights, bias=0.3)
    baseline = _rng_vectors(1, seed=3)[0]
    explainer = IntegratedGradientsExplainer(model, baseline, 0.5, steps=64, output="logit")
    for x in _rng_vectors(5, seed=4):
        attribution = explainer.attribute(x)
        expected = weights * (x.astype(np.float64) - baseline.astype(np.float64))
        np.testing.assert_allclose(attribution, expected, rtol=1e-3, atol=1e-4)


def test_zero_difference_gives_zero_attribution() -> None:
    model = _mlp()
    baseline = _rng_vectors(1)[0]
    explainer = IntegratedGradientsExplainer(model, baseline, 0.5)
    assert np.allclose(explainer.attribute(baseline), 0.0)


def test_deterministic_across_calls_and_instances() -> None:
    model = _mlp()
    baseline = _rng_vectors(1, seed=7)[0]
    x = _rng_vectors(1, seed=9)[0]
    first = IntegratedGradientsExplainer(model, baseline, 0.5).attribute(x)
    again = IntegratedGradientsExplainer(model, baseline, 0.5).attribute(x)
    assert np.array_equal(first, IntegratedGradientsExplainer(model, baseline, 0.5).attribute(x))
    assert np.array_equal(first, again)


def test_properties_warm_up_and_validation() -> None:
    model = _mlp()
    baseline = _rng_vectors(1)[0]
    explainer = IntegratedGradientsExplainer(model, baseline, 0.2465)
    assert explainer.baseline_probability == 0.2465
    assert explainer.n_features == N
    explainer.warm_up(_rng_vectors(1, seed=2)[0])
    with pytest.raises(ValueError, match="維度"):
        explainer.attribute(np.zeros(N + 1, dtype=np.float32))
    with pytest.raises(ValueError, match="steps"):
        IntegratedGradientsExplainer(model, baseline, 0.5, steps=0)


def test_runner_chunking_matches_single_pass() -> None:
    model = _mlp()
    data = _rng_vectors(50)
    whole = KerasModelRunner(model, chunk_size=1000).predict_proba(data)
    chunked = KerasModelRunner(model, chunk_size=7).predict_proba(data)
    assert whole.shape == (50,)
    assert whole.dtype == np.float64
    np.testing.assert_allclose(chunked, whole, atol=1e-6)
    assert ((whole > 0) & (whole < 1)).all()


def test_runner_edge_cases() -> None:
    runner = KerasModelRunner(_mlp())
    assert runner.predict_proba(np.empty((0, N), dtype=np.float32)).shape == (0,)
    with pytest.raises(ValueError, match="二維"):
        runner.predict_proba(np.zeros(N, dtype=np.float32))
    with pytest.raises(ValueError, match="chunk_size"):
        KerasModelRunner(_mlp(), chunk_size=0)
