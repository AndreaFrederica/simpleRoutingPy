import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from config.route_config import load_route_config
import modules
from modules.logger import logger
import context
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
route_status: dict[str, bool] = {}
route_lock = asyncio.Lock()

# 首次检查完成事件
first_check_done_event = asyncio.Event()


async def async_check_route(route: RouteEntry) -> bool:
    """异步执行路由检查"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, route.check_status)


async def continuous_route_check():
    """持续运行的路由检查任务"""
    global config_routes
    first_run = True

    while True:
        # 获取当前配置的副本以避免检查过程中配置变更
        with context.event_lock:
            current_routes = list(config_routes)

        # 批量检查所有路由
        tasks = [async_check_route(route) for route in current_routes]
        await asyncio.gather(*tasks)

        # 首次检查完成后触发事件
        if first_run:
            first_check_done_event.set()
            first_run = False

        # 按需调整检查间隔
        await asyncio.sleep(1)


async def main_loop():
    """主异步循环"""
    global config_routes
    config_routes = load_route_config()
    logger.info("load config done")

    # 启动后台检查任务
    check_task = asyncio.create_task(continuous_route_check())
    logger.info("create check_task")

    try:
        # 等待首次路由检查完成
        await first_check_done_event.wait()
        logger.info("First route check completed. Start applying routes.")

        while True:
            # 获取当前路由表并应用配置（无需等待后续检查）
            logger.debug("try get system route table")
            ip_routes = get_ip_route()
            logger.debug(f"System route table\n{ip_routes}")

            with context.event_lock:
                enable_config_route(ip_routes, config_routes)

            # 控制主循环频率
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Received exit signal, shutting down...")
    finally:
        check_task.cancel()
        with suppress(asyncio.CancelledError):
            await check_task


def main():
    logger.info("SimpleRoutingPy loading...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        main_task = loop.create_task(main_loop())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, exiting...")
    finally:
        if not main_task.done():  # type: ignore
            main_task.cancel()  # type: ignore
            with suppress(asyncio.CancelledError):
                loop.run_until_complete(main_task)  # type: ignore
        loop.close()


if __name__ == "__main__":
    main()
