from modules import ping_ng
import asyncio

async def test() -> None:
    rsp = await ping_ng.async_ping_with_return(host="192.168.202.1", count=10, delay=0,iface="eth5")
    print(rsp)

if __name__ == "__main__":
    #print(ping_ng.ping_with_return(host="192.168.202.1", count=10, delay=0))
    asyncio.run(test())
