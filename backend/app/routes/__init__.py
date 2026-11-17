from app.routes.analytics import analytics_bp
from app.routes.dashboard import dashboard_bp
from app.routes.datasets import datasets_bp
from app.routes.reports import reports_bp
from app.routes.transform import transform_bp
from app.routes.database import database_bp

api_blueprints = [dashboard_bp, datasets_bp, analytics_bp, reports_bp, transform_bp, database_bp]
