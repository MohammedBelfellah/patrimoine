from django.urls import path
from . import views


urlpatterns = [
    path("", views.public_map_view, name="public-map"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_router_view, name="dashboard"),
    path("dashboard/superadmin/", views.superadmin_view, name="dashboard-superadmin"),
    path("dashboard/admin/", views.admin_view, name="dashboard-admin"),
    path("dashboard/inspecteur/", views.inspecteur_view, name="dashboard-inspecteur"),
    path("dashboard/public/", views.public_dashboard_view, name="dashboard-public"),
]
