
#? 程序使用的协议号(缺省值)
app_protocal:int = 233
app_protocals:dict[str,int] = {
    "ping" : 234,
    "static" : 235,
}
#! 最大注册的协议号是254

#? 核验路由的协议
protocal_cheak:bool = True