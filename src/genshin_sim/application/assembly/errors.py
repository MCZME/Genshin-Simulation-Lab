"""仿真组装错误。"""


class AssemblyError(Exception):
    """运行时组装失败的基础错误。"""


class MissingRuntimeAssetError(AssemblyError):
    """必需的资产数据无法加载。"""


class MissingRuntimeHandlerError(AssemblyError):
    """必需的 handler_key 未在注册表中找到。"""


class InvalidRuntimePayloadError(AssemblyError):
    """资产 payload JSON 格式错误或暂不支持。"""
