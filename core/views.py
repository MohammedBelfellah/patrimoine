from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import EmailAuthenticationForm


class UserLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True
    authentication_form = EmailAuthenticationForm


login_view = UserLoginView.as_view()


def logout_view(request):
    logout(request)
    return redirect("public-map")


def _user_role(user):
    if user.is_superuser:
        return "superadmin"
    if user.groups.filter(name="ADMIN").exists():
        return "admin"
    if user.groups.filter(name="INSPECTEUR").exists():
        return "inspecteur"
    return "public"


@login_required
def dashboard_router_view(request):
    role = _user_role(request.user)
    if role == "superadmin":
        return redirect("dashboard-superadmin")
    if role == "admin":
        return redirect("dashboard-admin")
    if role == "inspecteur":
        return redirect("dashboard-inspecteur")
    return redirect("dashboard-public")


@login_required
def superadmin_view(request):
    if not request.user.is_superuser:
        return redirect("dashboard")
    return render(request, "core/dashboard_superadmin.html")


@login_required
def admin_view(request):
    if request.user.is_superuser:
        return redirect("dashboard-superadmin")
    if not request.user.groups.filter(name="ADMIN").exists():
        return redirect("dashboard")
    return render(request, "core/dashboard_admin.html")


@login_required
def inspecteur_view(request):
    if request.user.is_superuser:
        return redirect("dashboard-superadmin")
    if request.user.groups.filter(name="ADMIN").exists():
        return redirect("dashboard-admin")
    if not request.user.groups.filter(name="INSPECTEUR").exists():
        return redirect("dashboard")
    return render(request, "core/dashboard_inspecteur.html")


@login_required
def public_dashboard_view(request):
    if request.user.is_superuser or request.user.groups.filter(name__in=["ADMIN", "INSPECTEUR"]).exists():
        return redirect("dashboard")
    return render(request, "core/dashboard_public.html")


def public_map_view(request):
    return render(request, "core/public_map.html")
