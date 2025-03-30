# main.py
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
from venv import logger
import context
from modules.apply_routing import enable_config_route
from modules.dataclass import RouteEntry
from modules.routing import get_ip_route

# 命令行参数解析
debug_mode: bool = "-debug" in sys.argv
context.init(debug_mode=debug_mode)

# 异步执行器
executor = ThreadPoolExecutor(max_workers=10)

async def async_check_route(route: RouteEntry) -> bool:
    """异步执行路由检查"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, route.check_status)

async def continuous_route_check():
    """持续运行的路由检查任务"""
    while True:
        # 获取当前配置的副本以避免检查过程中配置变更
        with context.event_lock:
            current_routes = list(context.config_routes)
        
        # 批量检查所有路由
        tasks = [async_check_route(route) for route in current_routes]
        await asyncio.gather(*tasks)
        
        # 按需调整检查间隔（示例使用固定2秒）
        await asyncio.sleep(1)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 启动后台检查任务
        loop.create_task(continuous_route_check())
        
        # 主循环处理路由应用
        while True:
            # 获取当前路由表
            ip_routes = get_ip_route()
            
            # 应用路由配置（使用最新检查结果）
            with context.event_lock:
                enable_config_route(ip_routes, context.config_routes)
            
            # 控制主循环频率
            loop.run_until_complete(asyncio.sleep(2))
    except Exception as e:
        logger.exception(e)
    finally:
        loop.close()