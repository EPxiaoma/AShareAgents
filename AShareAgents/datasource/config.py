"""数据源配置模块。

管理数据供应商配置，支持默认配置和自定义覆盖。
"""

import AShareAgents.config as default_config
from typing import Dict, Optional

# 使用默认配置但允许覆盖
_config: Optional[Dict] = None


def initialize_config():
    """使用默认值初始化配置。"""
    global _config
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()


def set_config(config: Dict):
    """使用自定义值更新配置。"""
    global _config
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()
    _config.update(config)


def get_config() -> Dict:
    """获取当前配置的副本。"""
    if _config is None:
        initialize_config()
    return _config.copy()


# 使用默认配置初始化
initialize_config()
