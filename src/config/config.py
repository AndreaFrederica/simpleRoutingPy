from . import models


system_config = models.AppPathResolver(
    app_name=None,
    file_name="simplerouting.json",
    sub_dir="config"
)
log_file = models.TemporaryPathResolver(
    app_name="SimpleRouting",
    file_name="simplerouting.log",
    sub_dir="log"
)

#? 路由验证规则
ignore_protocal:bool = False

#? 退出时清理路由
clean_when_exit:bool = False
