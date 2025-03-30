import logging
import threading
from logging.handlers import RotatingFileHandler

import config

event_lock = threading.Lock()
route_status = {}
ping_warnings = set()

# 配置日志参数
log_path = config.log_file.file_path_str
max_log_size = config.max_log_size

# 初始化日志系统
logger = logging.getLogger('RouteLogger')
logger.setLevel(logging.DEBUG)  # 根记录器设置为最低级别

# 终端处理器配置（始终带日期）
console_handler = logging.StreamHandler()


# 文件处理器配置（保持不变）
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

main_handler = RotatingFileHandler(
    log_path,
    maxBytes=max_log_size,
    backupCount=3,
    encoding='utf-8'
)

def init(debug_mode:bool)-> None:
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)  # 级别控制
    console_format = '%(asctime)s - %(levelname)s - %(message)s'
    console_handler.setFormatter(logging.Formatter(console_format))
    
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(file_formatter)

    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(main_handler)