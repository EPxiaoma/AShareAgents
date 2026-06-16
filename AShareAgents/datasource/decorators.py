"""数据源类使用的装饰器辅助函数。"""

from __future__ import annotations


def decorate_all_methods(decorator):
    """将 ``decorator`` 应用于类中的全部可调用属性。"""
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator
