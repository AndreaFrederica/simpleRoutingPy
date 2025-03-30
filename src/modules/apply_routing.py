from collections import defaultdict
import config
from modules.dataclass import RouteEntry
from modules.routing import add_route, remove_route, replace_route
from modules.utilities import normalize_dest
from src.context import logger, route_status, event_lock


def apply_routes(
    inject_routes: list[RouteEntry],
    existing_routes: list[RouteEntry],
    remove_routes: list[RouteEntry],
) -> None:
    """
    执行实际路由变更操作，优化为优先替换目标地址相同的路由。
    执行顺序：
    1. 替换所有需要替换的路由
    2. 删除剩余需要移除的路由
    3. 添加剩余需要注入的路由
    """
    replace_inject = []  # 需要替换的新路由列表
    replace_remove = []  # 被替换的旧路由列表

    # 预处理：识别需要替换的路由对
    remove_routes_copy = list(remove_routes)
    inject_routes_copy = list(inject_routes)

    for a in remove_routes_copy:
        a_dest = normalize_dest(a.destination)
        for b in inject_routes_copy:
            b_dest = normalize_dest(b.destination)
            if a_dest == b_dest:
                # 记录替换对
                replace_inject.append(b)
                replace_remove.append(a)
                # 从原列表中移除已处理的路由
                if a in remove_routes:
                    remove_routes.remove(a)
                if b in inject_routes:
                    inject_routes.remove(b)
                # 防止重复处理
                inject_routes_copy.remove(b)
                break

    # 1. 执行替换操作
    for route in replace_inject:
        replace_route(route)

    # 2. 删除剩余需要移除的路由
    for route in remove_routes:
        remove_route(route)

    # 3. 添加剩余需要注入的路由
    for route in inject_routes:
        add_route(route)

    # 打印状态报告
    logger.debug("执行结果摘要：")
    logger.debug(f"成功替换 {len(replace_inject)} 条路由")
    logger.debug(f"成功移除 {len(remove_routes)} 条新路由")
    logger.debug(f"成功注入 {len(inject_routes)} 条新路由")
    logger.debug(f"系统已存在 {len(existing_routes)} 条有效路由")
    logger.debug(
        f"已清理 {len(remove_routes) + len(replace_remove)} 条失效路由（含替换）"
    )

    # 记录详细替换信息
    for old, new in zip(replace_remove, replace_inject):
        logger.debug(
            f"路由替换：{old.destination} ({old.gateway}) => {new.destination} ({new.gateway})"
        )


def enable_config_route(
    ip_routes: list[RouteEntry], config_routes: list[RouteEntry]
) -> None:
    global route_status

    # 跟踪状态变化
    for route in config_routes:
        current = route.useable
        previous = route_status.get(route.id, None)

        with event_lock:
            if previous is None:
                route_status[route.id] = current
                if current:
                    logger.info(f"接口上线: {route.interface}({route.id})")
                else:
                    logger.error(f"接口不可用: {route.interface}({route.id})")
            elif current != previous:
                route_status[route.id] = current
                if current:
                    logger.info(f"接口恢复: {route.interface}({route.id})")
                else:
                    logger.error(f"接口故障: {route.interface}({route.id})")

    # 后续原有路由处理逻辑保持不变...
    # 预处理：建立系统路由与配置路由的映射关系
    sys_route_config_map: dict[str, int] = {}
    for sys_route in ip_routes:
        # 查找匹配的配置路由（基于四个核心字段）
        matched_config = next((cr for cr in config_routes if cr == sys_route), None)

        # 记录匹配到的配置优先级（未匹配设为0）
        sys_route_config_map[sys_route.id] = (
            matched_config.priority if matched_config else config.uncached_priority
        )

    # 路由分组与处理逻辑（保持不变）
    destinations2routes = defaultdict(list[RouteEntry])
    for route in config_routes:
        if route.destination == "0.0.0.0/0":
            route.destination = "default"
        destinations2routes[route.destination].append(route)

    # 选择可用路由逻辑（保持不变）
    selected_routes: list[RouteEntry] = []
    failed_routes: list[RouteEntry] = []
    for dest, routes in destinations2routes.items():
        sorted_routes: list[RouteEntry] = sorted(routes, key=lambda x: x.priority)
        available: list[RouteEntry] = [r for r in sorted_routes if r.useable]
        if available:
            selected_routes.append(available[0])
        failed_routes.extend(r for r in sorted_routes if not r.useable)

    # 路由决策逻辑
    inject_routes: list[RouteEntry] = []
    remove_routes: list[RouteEntry] = []
    existing_routes: list[RouteEntry] = []

    # //// !TODO 这里有逻辑缺失 如果系统路由里存在一个优先级比需要写入的配置优先级低的路由 这个路由不会被删除（这个路由可能是被其他的配置项添加的）
    for candidate in selected_routes:
        # 查找匹配的系统路由
        matched_sys = next(
            (
                sr
                for sr in ip_routes
                if
                # sr == candidate
                normalize_dest(sr.destination) == normalize_dest(candidate.destination)
            ),
            None,
        )
        logger.debug(
            f"candidate: {candidate}",
        )

        if matched_sys:
            # 比较配置优先级与系统记录的优先级
            logger.debug(f"matched_sys: {matched_sys}")
            sys_prio = sys_route_config_map[matched_sys.id]
            logger.debug(sys_route_config_map)
            logger.debug(
                f"路由匹配: {candidate.id} (新优先级 {candidate.priority} | 旧 {sys_prio})"
            )
            if candidate.priority < sys_prio:
                logger.critical(
                    f"路由更新: {candidate.id} (新优先级 {candidate.priority} < 旧 {sys_prio})"
                )
                remove_routes.append(matched_sys)
                inject_routes.append(candidate)
            else:
                existing_routes.append(candidate)
        else:
            inject_routes.append(candidate)

    # 处理失效路由
    for failed in failed_routes:
        matched_sys = next((sr for sr in ip_routes if sr == failed), None)
        if matched_sys and matched_sys not in remove_routes:
            remove_routes.append(matched_sys)

    # 执行路由变更
    logger.debug("路由变更计划:")
    logger.debug(f"新增路由: {[r.id for r in inject_routes]}")
    logger.debug(f"删除路由: {[r.id for r in remove_routes]}")
    logger.debug(f"保留路由: {[r.id for r in existing_routes]}")
    logger.debug(f"失效路由: {[r.id for r in failed_routes]}")

    apply_routes(
        inject_routes=inject_routes,
        remove_routes=remove_routes,
        existing_routes=existing_routes,
    )
