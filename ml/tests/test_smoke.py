"""環境版本斷言：Python 與核心套件版本必須與 design.md 3.2.1 版本表完全相同。"""

import sys
from importlib.metadata import version

import keras
import numpy
import pandas
import tensorflow as tf


def test_python_version() -> None:
    assert sys.version_info[:3] == (3, 14, 8)


def test_pinned_package_versions() -> None:
    # tf.__version__ 顯示為 "2.22.0-rc0"，與發行版本 2.22.0rc0 為同一版本的不同寫法
    assert tf.__version__.replace("-", "") == "2.22.0rc0"
    assert version("tensorflow") == "2.22.0rc0"
    assert keras.__version__ == "3.16.0.dev2026101704"
    assert numpy.__version__ == "2.5.4"
    assert pandas.__version__ == "3.0.6"
    assert version("numpy") == "2.5.4"
    assert version("pandas") == "3.0.6"
    assert version("keras-nightly") == "3.16.0.dev2026101704"
