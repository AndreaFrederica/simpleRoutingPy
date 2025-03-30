import sys
import time

from config.route_config import load_route_config
import context
from context import logger, event_lock
from modules.apply_routing import enable_config_route
from modules.routing import get_ip_route

# 命令行参数解析
debug_mode: bool = "-debug" in sys.argv

context.init(debug_mode=debug_mode)

if __name__ == "__main__":
    # 初始化日志状态
    with event_lock:
        route_status = {}
        ping_warnings = set()
        config_routes = load_route_config()
        logger.info("load config done.")

    while True:
        ip_routes = get_ip_route()
        for route in config_routes:
            route.check_status()
        enable_config_route(ip_routes, config_routes)
        time.sleep(2)