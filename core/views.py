import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.db import DatabaseError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import EmailAuthenticationForm
from patrimoine.models import Inspection, Intervention, Patrimoine, Region


logger = logging.getLogger(__name__)


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
    return render(
        request, "core/dashboard_analytics.html", _dashboard_context(request.user)
    )


@login_required
def admin_view(request):
    if request.user.is_superuser:
        return redirect("dashboard-superadmin")
    if not request.user.groups.filter(name="ADMIN").exists():
        return redirect("dashboard")
    return render(
        request, "core/dashboard_analytics.html", _dashboard_context(request.user)
    )


@login_required
def inspecteur_view(request):
    if request.user.is_superuser:
        return redirect("dashboard-superadmin")
    if request.user.groups.filter(name="ADMIN").exists():
        return redirect("dashboard-admin")
    if not request.user.groups.filter(name="INSPECTEUR").exists():
        return redirect("dashboard")

    # Statistics for inspecteur
    my_inspections = Inspection.objects.filter(id_inspecteur=request.user)
    my_inspections_count = my_inspections.count()
    total_patrimoines = Patrimoine.objects.count()
    inspected_patrimoines_count = (
        my_inspections.values("id_patrimoine").distinct().count()
    )

    # Patrimoines inspected by this inspecteur
    inspected_patrimoines = (
        Patrimoine.objects.select_related("id_commune__id_province__id_region")
        .filter(inspection__id_inspecteur=request.user)
        .distinct()
        .order_by("nom_fr")[:10]
    )

    # Recent inspections
    recent_inspections = my_inspections.select_related("id_patrimoine").order_by(
        "-date_inspection"
    )[:5]

    context = {
        "my_inspections_count": my_inspections_count,
        "total_patrimoines": total_patrimoines,
        "inspected_patrimoines_count": inspected_patrimoines_count,
        "inspected_patrimoines": inspected_patrimoines,
        "recent_inspections": recent_inspections,
    }

    return render(request, "core/dashboard_inspecteur.html", context)


@login_required
def public_dashboard_view(request):
    if (
        request.user.is_superuser
        or request.user.groups.filter(name__in=["ADMIN", "INSPECTEUR"]).exists()
    ):
        return redirect("dashboard")
    return render(request, "core/dashboard_public.html")


def chatbot_view(request):
    return render(
        request,
        "core/chatbot.html",
        {"groq_configured": bool(settings.GROQ_API_KEY)},
    )


def public_map_view(request):
    data = []
    regions = Region.objects.none()

    try:
        patrimoines = Patrimoine.objects.select_related(
            "id_commune__id_province__id_region"
        ).all()

        for p in patrimoines:
            if (
                not p.id_commune
                or not p.id_commune.id_province
                or not p.id_commune.id_province.id_region
            ):
                continue

            region = p.id_commune.id_province.id_region
            province = p.id_commune.id_province
            commune = p.id_commune
            geom = json.loads(p.polygon_geom.geojson) if p.polygon_geom else None
            data.append(
                {
                    "id": p.id_patrimoine,
                    "nom": p.nom_fr,
                    "type": p.type_patrimoine,
                    "statut": p.statut,
                    "type_label": p.get_type_patrimoine_display(),
                    "statut_label": p.get_statut_display(),
                    "region_id": region.id_region,
                    "region_name": region.nom_region,
                    "province_name": province.nom_province,
                    "commune_name": commune.nom_commune,
                    "full_location": p.full_location,
                    "geom": geom,
                }
            )

        regions = Region.objects.all()
    except DatabaseError:
        # Keep home page available even when target DB schema/data is incomplete.
        logger.exception("Unable to load public map data from database")

    context = {
        "patrimoines_json": json.dumps(data),
        "regions": regions,
        "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
        "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
    }
    return render(request, "core/public_map.html", context)


PRIVATE_CHATBOT_TERMS = {
    "password",
    "mot de passe",
    "email",
    "e-mail",
    "mail",
    "user",
    "utilisateur",
    "admin",
    "superadmin",
    "inspecteur",
    "audit",
    "log",
    "file_path",
    "chemin",
    "uploaded_by",
    "created_by",
    "token",
    "secret",
    "smtp",
    "database_url",
    "api key",
    "clé api",
}


CHATBOT_SYSTEM_PROMPT = """
Tu es l'assistant public de Geo Patrimoine Hub.
Réponds en français simple, utile et concis.
Tu peux expliquer les données publiques du patrimoine fournies dans le contexte.
Tu ne dois jamais inventer des données absentes du contexte.
Tu ne dois jamais révéler ou deviner des informations privées: comptes utilisateurs,
emails, mots de passe, inspecteurs, administrateurs, journaux d'audit, chemins de fichiers,
clés, tokens, configuration serveur, données internes ou informations personnelles.
Si une demande vise ces informations, refuse brièvement et propose une alternative publique.
Si la question est générale, aide l'utilisateur, mais précise quand la réponse ne vient pas
directement de la base de données.
""".strip()


def _chatbot_private_request(message):
    text = message.lower()
    return any(term in text for term in PRIVATE_CHATBOT_TERMS)


def _chatbot_search_terms(message):
    return [
        term
        for term in re.findall(r"[\wÀ-ÿ'-]{3,}", message.lower())
        if term
        not in {
            "les",
            "des",
            "une",
            "dans",
            "avec",
            "pour",
            "quoi",
            "quel",
            "quelle",
            "combien",
            "patrimoine",
            "patrimoines",
        }
    ][:8]


def _public_patrimoine_context(message):
    stats = {
        "total_patrimoines": Patrimoine.objects.count(),
        "total_regions": Region.objects.count(),
        "total_inspections": Inspection.objects.count(),
        "total_interventions": Intervention.objects.count(),
        "patrimoines_par_type": list(
            Patrimoine.objects.values("type_patrimoine")
            .annotate(total=Count("id_patrimoine"))
            .order_by("type_patrimoine")
        ),
        "patrimoines_par_statut": list(
            Patrimoine.objects.values("statut")
            .annotate(total=Count("id_patrimoine"))
            .order_by("statut")
        ),
        "patrimoines_par_region": list(
            Patrimoine.objects.values("id_commune__id_province__id_region__nom_region")
            .annotate(total=Count("id_patrimoine"))
            .order_by("id_commune__id_province__id_region__nom_region")
        ),
    }

    terms = _chatbot_search_terms(message)
    query = Q()
    for term in terms:
        query |= (
            Q(nom_fr__icontains=term)
            | Q(nom_ar__icontains=term)
            | Q(description__icontains=term)
            | Q(type_patrimoine__icontains=term)
            | Q(statut__icontains=term)
            | Q(id_commune__nom_commune__icontains=term)
            | Q(id_commune__id_province__nom_province__icontains=term)
            | Q(id_commune__id_province__id_region__nom_region__icontains=term)
        )

    patrimoines = Patrimoine.objects.select_related(
        "id_commune__id_province__id_region"
    )
    if query:
        patrimoines = patrimoines.filter(query)
    patrimoines = patrimoines.order_by("nom_fr")[:12]

    items = []
    for patrimoine in patrimoines:
        commune = patrimoine.id_commune
        province = commune.id_province if commune else None
        region = province.id_region if province else None
        centroid = None
        if patrimoine.centroid_geom:
            centroid = {
                "lat": patrimoine.centroid_geom.y,
                "lng": patrimoine.centroid_geom.x,
            }
        items.append(
            {
                "nom_fr": patrimoine.nom_fr,
                "nom_ar": patrimoine.nom_ar,
                "description": patrimoine.description,
                "type": patrimoine.get_type_patrimoine_display(),
                "statut": patrimoine.get_statut_display(),
                "region": region.nom_region if region else "",
                "province": province.nom_province if province else "",
                "commune": commune.nom_commune if commune else "",
                "centroid": centroid,
            }
        )

    return {"stats": stats, "resultats_publics": items}


def _groq_chat(message, context):
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": CHATBOT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Question utilisateur:\n"
                    f"{message}\n\n"
                    "Contexte public autorisé depuis la base de données:\n"
                    f"{json.dumps(context, ensure_ascii=False, default=str)}"
                ),
            },
        ],
        "temperature": 0.2,
        "max_completion_tokens": 700,
    }
    request = Request(
        settings.GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "GeoPatrimoineHub/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


@require_POST
def chatbot_api(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Requête invalide."}, status=400)

    message = str(payload.get("message", "")).strip()
    if not message:
        return JsonResponse({"error": "Écrivez une question."}, status=400)
    if len(message) > 800:
        return JsonResponse({"error": "Question trop longue."}, status=400)

    if _chatbot_private_request(message):
        return JsonResponse(
            {
                "answer": (
                    "Je ne peux pas fournir d'informations privées ou internes. "
                    "Je peux vous aider avec les données publiques des patrimoines, "
                    "les régions, les types, les statuts et les statistiques générales."
                )
            }
        )

    try:
        context = _public_patrimoine_context(message)
    except DatabaseError:
        logger.exception("Unable to build public chatbot context")
        return JsonResponse(
            {"answer": "Je n'arrive pas à consulter la base de données pour le moment."},
            status=503,
        )

    if not settings.GROQ_API_KEY:
        return JsonResponse(
            {
                "answer": (
                    "Le chatbot IA n'est pas encore configuré. Ajoutez GROQ_API_KEY "
                    "dans .env, puis redémarrez le service web."
                )
            },
            status=503,
        )

    try:
        answer = _groq_chat(message, context)
    except HTTPError as exc:
        logger.exception("Groq API HTTP error: %s", exc)
        return JsonResponse(
            {"answer": "Groq a refusé la requête. Vérifiez la clé API et le modèle."},
            status=502,
        )
    except (URLError, TimeoutError, KeyError, json.JSONDecodeError):
        logger.exception("Groq API request failed")
        return JsonResponse(
            {"answer": "Le service IA est momentanément indisponible."},
            status=502,
        )

    return JsonResponse({"answer": answer})


def _dashboard_context(user):
    try:
        total_patrimoines = Patrimoine.objects.count()
        total_inspections = Inspection.objects.count()
        total_interventions = Intervention.objects.count()

        by_type = list(
            Patrimoine.objects.values("type_patrimoine")
            .annotate(total=Count("id_patrimoine"))
            .order_by("type_patrimoine")
        )
        by_statut = list(
            Patrimoine.objects.values("statut")
            .annotate(total=Count("id_patrimoine"))
            .order_by("statut")
        )
        by_region = list(
            Patrimoine.objects.values("id_commune__id_province__id_region__nom_region")
            .annotate(total=Count("id_patrimoine"))
            .order_by("id_commune__id_province__id_region__nom_region")
        )
        inspection_state = list(
            Inspection.objects.values("etat")
            .annotate(total=Count("id_inspection"))
            .order_by("etat")
        )
        intervention_status = list(
            Intervention.objects.values("statut")
            .annotate(total=Count("id_intervention"))
            .order_by("statut")
        )

        centroids = []
        for p in Patrimoine.objects.exclude(centroid_geom__isnull=True).only(
            "id_patrimoine", "nom_fr", "type_patrimoine", "centroid_geom"
        )[:1000]:
            if not p.centroid_geom:
                continue
            geo = json.loads(p.centroid_geom.geojson)
            centroids.append(
                {
                    "id": p.id_patrimoine,
                    "nom": p.nom_fr,
                    "type": p.type_patrimoine,
                    "coords": geo.get("coordinates", []),
                }
            )
    except DatabaseError:
        logger.exception("Unable to load dashboard analytics data from database")
        total_patrimoines = 0
        total_inspections = 0
        total_interventions = 0
        by_type = []
        by_statut = []
        by_region = []
        inspection_state = []
        intervention_status = []
        centroids = []

    return {
        "is_superadmin": user.is_superuser,
        "total_patrimoines": total_patrimoines,
        "total_inspections": total_inspections,
        "total_interventions": total_interventions,
        "by_type_json": json.dumps(by_type),
        "by_statut_json": json.dumps(by_statut),
        "by_region_json": json.dumps(by_region),
        "inspection_state_json": json.dumps(inspection_state),
        "intervention_status_json": json.dumps(intervention_status),
        "centroids_json": json.dumps(centroids),
    }
