from . import config
from .config import system_config, log_file

max_log_size = 5 * 1024 * 1024  # 5MB
uncached_priority = 255