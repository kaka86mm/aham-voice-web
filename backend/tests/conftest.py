"""共享 pytest fixtures。

原项目零测试，本文件随 Task 1 建立，后续 task 按需扩充。
"""
import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """把 AHAMVOICE_HOME / AHAMVOICE_MODELS_DIR 指向临时目录，隔离测试不污染真实数据。

    注：config.py 的路径常量在 import 时求值。Task 3a 抽出 config.py 后，
    此 fixture 末尾会加 importlib.reload(config) 让 env 生效。
    当前 Task 1 阶段 config 还在 main.py，此 fixture 仅供后续 task 使用。
    """
    monkeypatch.setenv("AHAMVOICE_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AHAMVOICE_MODELS_DIR", str(tmp_path / "models"))
    return tmp_path
