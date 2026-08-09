"""RunCrew 本地跑步数据对话与工程观测界面。"""

from runcrew.web.dashboard import DemoDashboardService
from runcrew.web.server import DemoApplication, serve_demo

__all__ = ["DemoApplication", "DemoDashboardService", "serve_demo"]
