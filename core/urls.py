from django.urls import path
from . import views
from patrimoine import views as pat_views


urlpatterns = [
    path("", views.public_map_view, name="public-map"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_router_view, name="dashboard"),
    path("dashboard/superadmin/", views.superadmin_view, name="dashboard-superadmin"),
    path("dashboard/admin/", views.admin_view, name="dashboard-admin"),
    path("dashboard/inspecteur/", views.inspecteur_view, name="dashboard-inspecteur"),
    path("dashboard/public/", views.public_dashboard_view, name="dashboard-public"),
    path("users/", pat_views.user_management, name="user-management"),
    path("users/<int:user_id>/toggle/<str:group_name>/", pat_views.toggle_user_group, name="toggle-user-group"),
    path("audit/", pat_views.audit_log, name="audit-log"),
]
