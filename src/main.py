import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from config.route_config import load_route_config
import modules
from modules.logger import logger
import config
from modules.apply_routing import enable_config_route
from modules.dataclass import RouteEntry
from modules.routing import get_ip_route

# 命令行参数解析
debug_mode: bool = "-debug" in sys.argv or "--debug" in sys.argv
modules.logger.init(debug_mode=debug_mode)

# 异步执行器
executor = ThreadPoolExecutor(max_workers=10)
config_routes: list[RouteEntry]

# 存储每个路由的检查任务和状态
route_tasks: dict[str, asyncio.Task] = {}
route_initial_checks: dict[str, asyncio.Event] = {}  # 新增路由级首次检查事件
route_lock = asyncio.Lock()

# 首次检查完成事件
first_check_done_event = asyncio.Event()

# 新增：当任意接口状态变化时触发此事件
interface_change_event = asyncio.Event()


#定义退出清理函数
def exitFunc() -> None:
    """退出清理函数"""
    modules.routing.clean()

async def monitor_route(route: RouteEntry, initial_check_event: asyncio.Event):
    """独立监控单个路由的异步任务（增加首次检查事件参数）"""
    try:
        await route.check_status()
        # 标记首次检查完成
        initial_check_event.set()
        logger.debug(f"路由 {route.id} 首次检查完成")
        prev_status: bool | None = route.useable  # 保存初始状态
        interface_change_event.set()
        # 持续监控循环
        while True:
            await route.check_status()
            if route.useable != prev_status:
                # 当接口状态发生变化时，触发全局事件
                interface_change_event.set()
                prev_status = route.useable
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"路由 {route.id} 监控异常: {str(e)}")
        initial_check_event.set()  # 确保异常时也能触发事件
        raise

async def continuous_route_check():
    """启动所有路由的独立监控任务并等待首次检查"""
    global config_routes, route_tasks, route_initial_checks

    check_events = []

    async with route_lock:
        # 初始化路由监控任务
        for route in config_routes:
            if route.id not in route_tasks:
                # 为每个路由创建专属首次检查事件
                initial_event = asyncio.Event()
                route_initial_checks[route.id] = initial_event
                check_events.append(initial_event)
                task = asyncio.create_task(monitor_route(route, initial_event))
                route_tasks[route.id] = task
                logger.info(f"已启动路由监控: {route.id}")

    # 等待所有路由完成首次检查
    if check_events:
        await asyncio.gather(*[event.wait() for event in check_events], return_exceptions=True)
    
    # 触发全局完成事件
    first_check_done_event.set()

async def main_loop():
    """主异步循环"""
    global config_routes, interface_change_event
    logger.info(f"save log file to {config.log_file.file_path_str}")
    logger.info(f"load config from {config.system_config.file_path_str}")
    config_routes = load_route_config()
    logger.info("load config done")
    
    # 启动所有路由的监控任务
    await continuous_route_check()
    
    try:
        # 等待首次检查完成
        await first_check_done_event.wait()
        logger.info("First check completed. Start applying routes.")
        
        while True:
            # 控制主循环频率
            # await asyncio.sleep(1)
            await interface_change_event.wait()
            interface_change_event.clear()
            # 获取当前路由表
            logger.debug("try get system route table")
            ip_routes = get_ip_route()
            logger.debug(f"System route table\n{ip_routes}")
            
            # 应用路由配置（使用最新检查状态）
            async with route_lock:
                enable_config_route(ip_routes, config_routes)
            
    except asyncio.CancelledError:
        logger.info("Received exit signal, shutting down...")
    finally:
        # 取消所有路由监控任务
        async with route_lock:
            for task in route_tasks.values():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*route_tasks.values())


def main() -> None:
    logger.info("SimpleRoutingPy loading...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    main_task:None|asyncio.Task = None
    try:
        main_task = loop.create_task(main_loop())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, exiting...")
    finally:
        if main_task:
            if not main_task.done():
                main_task.cancel()
                with suppress(asyncio.CancelledError):
                    loop.run_until_complete(main_task)
        loop.close()
        exitFunc()
        

if __name__ == "__main__":
    main()
