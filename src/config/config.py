from ast import mod
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
