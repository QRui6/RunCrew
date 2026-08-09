"""RunCrew 本地只读演示界面。"""

from runcrew.web.dashboard import DemoDashboardService
from runcrew.web.server import DemoApplication, serve_demo

__all__ = ["DemoApplication", "DemoDashboardService", "serve_demo"]
