"""配置加载与校验错误。"""


class ConfigError(ValueError):
    """无效仿真配置的基础错误。"""


class ConfigFileError(ConfigError):
    """配置文件无法读取或解析。"""
