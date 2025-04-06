from pyroute2 import IPRoute

ipr = IPRoute()
# 获取接口索引
idx_list = ipr.link_lookup(ifname="eth0")
if idx_list:
    idx = idx_list[0]
    # 获取该接口的路由信息，其中 dst_len 为 0 表示默认路由
    routes = ipr.get_routes(oif=idx, dst_len=0)
    for route in routes:
        gateway = route.get_attr("RTA_GATEWAY")
        if gateway:
            print("Gateway for eth0:", gateway)
else:
    print("Interface eth0 not found")


from pyroute2 import IPRoute

ipr = IPRoute()
routes = ipr.get_routes()

# 一个简单的协议映射，可以根据实际情况扩充
protocol_names = {
    1: "unspec",
    2: "kernel",
    3: "boot",
    4: "static",
    8: "GATED",     #Apparently, GateD
    9: "RA",        #RDISC/ND router advertisements
    10: "MRT",      #Merit MRT
    11: "ZEBRA",    #Zebra
    12: "BIRD",     #BIRD
    13: "DNROUTED", #DECnet routing daemon
    14: "XORP",     #XORP
    15: "NTK",      #Netsukuku
    16: "DHCP",     #DHCP client
    17: "MROUTED",  #Multicast daemon
    42: "BABEL",    #Babel daemon
    186: "BGP",     #BGP Routes
    187: "ISIS",    #ISIS Routes
    188: "OSPF",    #OSPF Routes
    189: "RIP",     #RIP Routes
    192: "EIGRP",   #EIGRP Routes
    
    233: "SimpleRouting"
    # 常见的其他协议号码也可以加入，比如 8: "RIP" 等
}

for route in routes:
    # 目的地址，如果没有 RTA_DST 则为默认路由
    dst = route.get_attr("RTA_DST")
    dst_len = route.get("dst_len", "")
    # 网关地址
    gateway = route.get_attr("RTA_GATEWAY")
    # 获取出口接口索引并转换为接口名称
    oif = route.get("oif")
    iface = None
    if oif:
        links = ipr.get_links(oif)
        if links:
            iface = links[0].get_attr("IFLA_IFNAME")
    # 获取路由的协议（数字）
    protocol = route.get("proto")
    protocol_name = protocol_names.get(protocol, f"{protocol}")

    if dst is None:
        dst = "default"
    print(
        f"Destination: {dst}/{dst_len}, Gateway: {gateway}, Interface: {iface}, Protocol: {protocol_name}"
    )
