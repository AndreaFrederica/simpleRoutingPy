import subprocess
from modules.dataclass import RouteEntry
from context import logger


def get_ip_route() -> list[RouteEntry]:
    result = subprocess.run(["ip", "route"], capture_output=True, text=True)
    routes = []
    i = 0

    for line in result.stdout.splitlines():
        parts = line.split()
        dest = parts[0]
        gw = None
        iface = None
        metric = 0
        proto = None

        if "via" in parts:
            gw = parts[parts.index("via") + 1]

        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]

        if "metric" in parts:
            metric = int(parts[parts.index("metric") + 1])

        if "proto" in parts:
            proto = parts[parts.index("proto") + 1]

        if iface:
            routes.append(
                RouteEntry(
                    id=f"sys_route{i}",
                    destination=dest,
                    gateway=gw,
                    interface=iface,
                    metric=metric,
                    priority=0,
                    proto=proto,
                    rule=None,
                    useable=None,
                )
            )
        i += 1

    return routes





def add_route(route: RouteEntry) -> bool:
    """通过ip route命令添加路由"""
    # 转换默认路由表示方式
    dest = route.destination
    if dest == "default":
        dest = "0.0.0.0/0"

    # 构建基础命令
    cmd = ["ip", "route", "add", dest]

    # 添加网关参数
    if route.gateway:
        cmd.extend(["via", route.gateway])

    # 添加设备参数
    cmd.extend(["dev", route.interface])

    # 添加metric参数
    if route.metric > 0:
        cmd.extend(["metric", str(route.metric)])
    logger.info(cmd)
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.critical(f"[OK] 已添加路由: {route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        logger.error(f"[ERR] 添加路由失败 {route.id}: {error_msg}")
        if(error_msg == "Error: Nexthop has invalid gateway."):
            try:
                cmd.remove("via"); cmd.remove(str(route.gateway))
                logger.debug(cmd)
                result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
                )
                logger.critical(f"[OK] 已替换路由: {route.id}")
                return True
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip()
                # 特殊处理路由不存在的情况
                if "No such process" in error_msg or "No such file or directory" in error_msg:
                    logger.warning(f"[WARN] 路由不存在，尝试新增: {route.id}")
                    return add_route(route)
                logger.error(f"[ERR] 第二次尝试替换路由失败 {route.id}: {error_msg}")
            pass
        return False


def remove_route(route: RouteEntry) -> bool:
    """通过ip route命令删除路由"""
    # 转换默认路由表示方式
    dest = route.destination
    if dest == "default":
        dest = "0.0.0.0/0"

    # 构建基础命令
    cmd = ["ip", "route", "del", dest]

    # 添加网关参数（提升删除准确性）
    if route.gateway:
        cmd.extend(["via", route.gateway])

    # 添加设备参数（提升删除准确性）
    cmd.extend(["dev", route.interface])
    logger.info(cmd)
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.critical(f"[OK] 已删除路由: {route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        logger.error(f"[ERR] 删除路由失败 {route.id}: {error_msg}")
        return False

def replace_route(new_route: RouteEntry) -> bool:
    """通过ip route命令替换路由（原子操作）"""
    # 统一目标地址格式
    dest = new_route.destination
    if dest == "default":
        dest = "0.0.0.0/0"

    # 构建replace命令（支持新增或覆盖）
    cmd = ["ip", "route", "replace", dest]

    # 添加网关参数
    if new_route.gateway:
        cmd.extend(["via", new_route.gateway])

    # 添加设备参数
    cmd.extend(["dev", new_route.interface])

    # 添加metric参数
    if new_route.metric > 0:
        cmd.extend(["metric", str(new_route.metric)])
        logger.info(cmd)
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.critical(f"[OK] 已替换路由: {new_route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        # 特殊处理路由不存在的情况
        if "No such process" in error_msg or "No such file or directory" in error_msg:
            logger.warning(f"[WARN] 路由不存在，尝试新增: {new_route.id}")
            return add_route(new_route)
        logger.error(f"[ERR] 替换路由失败 {new_route.id}: {error_msg}")
        if(error_msg == "Error: Nexthop has invalid gateway."):
            try:
                cmd.remove("via"); cmd.remove(str(new_route.gateway))
                logger.debug(cmd)
                result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
                )
                logger.critical(f"[OK] 已替换路由: {new_route.id}")
                return True
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip()
                # 特殊处理路由不存在的情况
                if "No such process" in error_msg or "No such file or directory" in error_msg:
                    logger.warning(f"[WARN] 路由不存在，尝试新增: {new_route.id}")
                    return add_route(new_route)
                logger.error(f"[ERR] 第二次尝试替换路由失败 {new_route.id}: {error_msg}")
            pass
        return False