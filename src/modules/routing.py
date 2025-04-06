import re
import subprocess
from typing import Optional
import config
import config.protocal
from modules.dataclass import RouteEntry
from modules.logger import logger


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
            if proto.isdigit():
                proto_int = int(proto)
                if(proto_int in config.app_protocals.values()):
                    proto = config.proro_int2name[proto_int]
                else:
                    ...

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

    # 添加app自己的协议号
    if(route.proto):
        if(route.proto in config.app_protocals.keys()):
            cmd.extend(["protocol" , str(config.app_protocals[route.proto])])
        else:
            #?缺省值
            cmd.extend(["protocol" , str(config.app_protocal)])
    else:
        #?缺省值
        cmd.extend(["protocol" , str(config.app_protocal)])

    # 添加metric参数
    if route.metric > 0:
        cmd.extend(["metric", str(route.metric)])
    logger.info(cmd)
    try:
        logger.debug(f"cmd={str(cmd)}")
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.critical(f"[OK] 已添加路由: {route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        logger.error(f"[ERR] 添加路由失败 {route.id}: {error_msg}")
        if error_msg == "Error: Nexthop has invalid gateway.":
            try:
                cmd.remove("via")
                cmd.remove(str(route.gateway))
                logger.debug(f"cmd={str(cmd)}")
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                logger.critical(f"[OK] 已替换路由: {route.id}")
                return True
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip()
                # 特殊处理路由不存在的情况
                if (
                    "No such process" in error_msg
                    or "No such file or directory" in error_msg
                ):
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
        logger.debug(f"cmd={str(cmd)}")
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
    
    # 添加app自己的协议号
    if(new_route.proto):
        if(new_route.proto in config.app_protocals.keys()):
            cmd.extend(["protocol" , str(config.app_protocals[new_route.proto])])
        else:
            #?缺省值
            cmd.extend(["protocol" , str(config.app_protocal)])
    else:
        #?缺省值
        cmd.extend(["protocol" , str(config.app_protocal)])

    # 添加metric参数
    if new_route.metric > 0:
        cmd.extend(["metric", str(new_route.metric)])
        logger.info(cmd)
    try:
        logger.debug(f"cmd={str(cmd)}")
        result = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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
        if error_msg == "Error: Nexthop has invalid gateway.":
            try:
                cmd.remove("via")
                cmd.remove(str(new_route.gateway))
                logger.debug(f"cmd={str(cmd)}")
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                logger.critical(f"[OK] 已替换路由: {new_route.id}")
                return True
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip()
                # 特殊处理路由不存在的情况
                if (
                    "No such process" in error_msg
                    or "No such file or directory" in error_msg
                ):
                    logger.warning(f"[WARN] 路由不存在，尝试新增: {new_route.id}")
                    return add_route(new_route)
                logger.error(
                    f"[ERR] 第二次尝试替换路由失败 {new_route.id}: {error_msg}"
                )
            pass
        return False

def get_interface_gateway(iface: str) -> Optional[str]:
    """
    获取指定接口的网关地址。如果存在 "default via ..." 则返回 default 的网关，
    否则返回第一行的目的地址（例如 "10.148.64.1"）。
    如果命令执行失败或没有匹配到，返回 None。
    """
    try:
        output = subprocess.check_output(
            ["ip", "route", "show", "dev", iface],
            encoding="utf-8"
        )
    except subprocess.CalledProcessError:
        return None

    # 按行解析输出
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # 如果行以 "default via" 开头
        m = re.search(r"default via (\S+)", line)
        if m:
            return m.group(1)
        else:
            # 如果不是 default 路由，则假定第一段是网关/目的地址
            tokens = line.split()
            if tokens:
                return tokens[0]
    return None

def clean() -> None:
    """清理所有自己产生的路由规则"""
    routes: list[RouteEntry] = get_ip_route()
    if config.clean_when_exit:
        for route in routes:
            if(route.proto == str(config.app_protocal)):
                remove_route(route)
                logger.critical(f"已清理{route}")
            if(route.proto in list(map(str, config.app_protocals.keys()))):
                remove_route(route)
                logger.critical(f"已清理{route}")