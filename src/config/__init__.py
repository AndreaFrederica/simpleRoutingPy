from . import config, protocal
from .config import system_config, log_file, clean_when_exit, ignore_protocal

from .protocal import app_protocal, app_protocals

proro_int2name = {v: k for k, v in app_protocals.items()}

max_log_size = 5 * 1024 * 1024  # 5MB
uncached_priority = 255