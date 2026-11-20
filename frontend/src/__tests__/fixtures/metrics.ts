// 測試用的成效資料（結構同 design.md 6.5.4）；刻意使用與正式 metrics.json 不同的數字，
// 確認畫面數字來自 API 而非寫死
import type { MetricsResponse, ModelResult } from '../../api/metrics'

const roc = { fpr: [0, 0.1, 0.5, 1], tpr: [0, 0.4, 0.8, 1] }

function model(key: ModelResult['key'], overrides: Partial<ModelResult['metrics']>): ModelResult {
  return {
    key,
    display_name: key === 'keras_mlp' ? 'Keras 神經網路' : '邏輯迴歸',
    decision_threshold: key === 'keras_mlp' ? 0.41 : 0.33,
    metrics: { roc_auc: 0.8, precision: 0.5, recall: 0.7, f1: 0.6, accuracy: 0.75, ...overrides },
    confusion_matrix: { tn: 700, fp: 300, fn: 90, tp: 310 },
    roc_curve: roc,
  }
}

export function makeMetrics(overrides: Partial<MetricsResponse> = {}): MetricsResponse {
  return {
    primary_model: 'keras_mlp',
    model_version: '20260101-deadbeef',
    trained_at: '2026-01-02T03:04:05Z',
    random_seed: 7,
    imbalance_strategy: 'threshold_tuning',
    target_recall: 0.8,
    dataset: {
      train_size: 1000,
      validation_size: 250,
      test_size: 400,
      test_churn_rate: 0.3,
      majority_class_accuracy: 0.7,
    },
    models: [
      model('logistic_regression', { roc_auc: 0.81, recall: 0.72 }),
      model('keras_mlp', { roc_auc: 0.79, recall: 0.72, precision: 0.55 }),
    ],
    decision_threshold: 0.41,
    imbalance_experiment: [],
    warnings: [],
    ...overrides,
  }
}
