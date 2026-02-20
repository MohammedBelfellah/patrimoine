from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Commune, Document, Inspection, InspectionModificationRequest, Intervention, Patrimoine, Province, Region


def _can_edit(user):
    """Check if user can edit patrimoine (admin/editeur)."""
    return user.is_superuser or user.groups.filter(name="ADMIN").exists()


def _can_view(user):
    """Check if user can view patrimoine (all authenticated users)."""
    return user.is_authenticated


@login_required
def patrimoine_list(request):
    """List all patrimoines with search/filter."""
    if not _can_view(request.user):
        return redirect("public-map")

    patrimoines = Patrimoine.objects.select_related("id_commune__id_province__id_region").all()

    # Filters
    search = request.GET.get("search", "").strip()
    if search:
        patrimoines = patrimoines.filter(nom_fr__icontains=search)

    type_filter = request.GET.get("type", "").strip()
    if type_filter:
        patrimoines = patrimoines.filter(type_patrimoine=type_filter)

    statut_filter = request.GET.get("statut", "").strip()
    if statut_filter:
        patrimoines = patrimoines.filter(statut=statut_filter)

    region_filter = request.GET.get("region", "").strip()
    if region_filter:
        patrimoines = patrimoines.filter(id_commune__id_province__id_region__id_region=region_filter)

    context = {
        "patrimoines": patrimoines,
        "can_edit": _can_edit(request.user),
        "regions": Region.objects.all(),
        "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
        "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
    }
    return render(request, "patrimoine/patrimoine_list.html", context)


@login_required
def patrimoine_detail(request, id_patrimoine):
    """Display patrimoine details."""
    if not _can_view(request.user):
        return redirect("public-map")

    patrimoine = get_object_or_404(Patrimoine, id_patrimoine=id_patrimoine)
    context = {
        "patrimoine": patrimoine,
        "can_edit": _can_edit(request.user),
    }
    return render(request, "patrimoine/patrimoine_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def patrimoine_create(request):
    """Create new patrimoine."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")

    if request.method == "POST":
        try:
            nom_fr = request.POST.get("nom_fr", "").strip()
            nom_ar = request.POST.get("nom_ar", "").strip()
            description = request.POST.get("description", "").strip()
            type_patrimoine = request.POST.get("type_patrimoine", "").strip()
            statut = request.POST.get("statut", "EN_ETUDE").strip()
            reference_administrative = request.POST.get("reference_administrative", "").strip()
            geojson_str = request.POST.get("geojson", "").strip()
            id_commune = request.POST.get("id_commune", "").strip()

            if not all([nom_fr, type_patrimoine, id_commune, geojson_str]):
                context = {
                    "error": "Champs obligatoires manquants (Nom, Type, Commune, Polygone)",
                    "regions": Region.objects.all(),
                    "provinces": Province.objects.all(),
                    "communes": Commune.objects.all(),
                    "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
                    "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
                }
                return render(request, "patrimoine/patrimoine_form.html", context)

            commune = Commune.objects.get(id_commune=id_commune)
            polygon_geom = GEOSGeometry(geojson_str)

            # Use raw SQL to avoid GENERATED column issue with centroid_geom
            with connection.cursor() as cursor:
                wkt = polygon_geom.wkt
                cursor.execute(
                    """
                    INSERT INTO patrimoine 
                    (nom_fr, nom_ar, description, type_patrimoine, statut, reference_administrative, 
                     polygon_geom, id_commune, created_by, created_at, updated_at)
                    VALUES 
                    (%s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, NOW(), NOW())
                    RETURNING id_patrimoine
                    """,
                    [
                        nom_fr,
                        nom_ar or None,
                        description or None,
                        type_patrimoine,
                        statut,
                        reference_administrative or None,
                        wkt,
                        commune.id_commune,
                        request.user.id,
                    ],
                )
                patrimoine_id = cursor.fetchone()[0]

            return redirect("patrimoine-detail", id_patrimoine=patrimoine_id)
        except Exception as e:
            context = {
                "error": str(e),
                "regions": Region.objects.all(),
                "provinces": Province.objects.all(),
                "communes": Commune.objects.all(),
                "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
                "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
            }
            return render(request, "patrimoine/patrimoine_form.html", context)

    context = {
        "regions": Region.objects.all(),
        "provinces": Province.objects.all(),
        "communes": Commune.objects.all(),
        "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
        "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
    }
    return render(request, "patrimoine/patrimoine_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def patrimoine_edit(request, id_patrimoine):
    """Edit existing patrimoine."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")

    patrimoine = get_object_or_404(Patrimoine, id_patrimoine=id_patrimoine)

    if request.method == "POST":
        try:
            nom_fr = request.POST.get("nom_fr", patrimoine.nom_fr).strip()
            nom_ar = request.POST.get("nom_ar", patrimoine.nom_ar or "").strip()
            description = request.POST.get("description", patrimoine.description or "").strip()
            type_patrimoine = request.POST.get("type_patrimoine", patrimoine.type_patrimoine).strip()
            statut = request.POST.get("statut", patrimoine.statut).strip()
            reference_administrative = request.POST.get("reference_administrative", patrimoine.reference_administrative or "").strip()
            geojson_str = request.POST.get("geojson", "").strip()
            id_commune = request.POST.get("id_commune", "").strip()

            # Use raw SQL to avoid GENERATED column issue
            with connection.cursor() as cursor:
                if geojson_str:
                    # Update with new geometry
                    polygon_geom = GEOSGeometry(geojson_str)
                    wkt = polygon_geom.wkt
                    cursor.execute(
                        """
                        UPDATE patrimoine 
                        SET nom_fr = %s, nom_ar = %s, description = %s, 
                            type_patrimoine = %s, statut = %s, reference_administrative = %s,
                            polygon_geom = ST_GeomFromText(%s, 4326), id_commune = %s, updated_at = NOW()
                        WHERE id_patrimoine = %s
                        """,
                        [
                            nom_fr,
                            nom_ar or None,
                            description or None,
                            type_patrimoine,
                            statut,
                            reference_administrative or None,
                            wkt,
                            id_commune or patrimoine.id_commune.id_commune,
                            patrimoine.id_patrimoine,
                        ],
                    )
                else:
                    # Update without changing geometry
                    cursor.execute(
                        """
                        UPDATE patrimoine 
                        SET nom_fr = %s, nom_ar = %s, description = %s, 
                            type_patrimoine = %s, statut = %s, reference_administrative = %s,
                            id_commune = %s, updated_at = NOW()
                        WHERE id_patrimoine = %s
                        """,
                        [
                            nom_fr,
                            nom_ar or None,
                            description or None,
                            type_patrimoine,
                            statut,
                            reference_administrative or None,
                            id_commune or patrimoine.id_commune.id_commune,
                            patrimoine.id_patrimoine,
                        ],
                    )

            return redirect("patrimoine-detail", id_patrimoine=patrimoine.id_patrimoine)
        except Exception as e:
            context = {
                "patrimoine": patrimoine,
                "error": str(e),
                "regions": Region.objects.all(),
                "provinces": Province.objects.filter(id_region=patrimoine.id_commune.id_province.id_region),
                "communes": Commune.objects.filter(id_province=patrimoine.id_commune.id_province),
                "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
                "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
            }
            return render(request, "patrimoine/patrimoine_form.html", context)

    context = {
        "patrimoine": patrimoine,
        "regions": Region.objects.all(),
        "provinces": Province.objects.filter(id_region=patrimoine.id_commune.id_province.id_region),
        "communes": Commune.objects.filter(id_province=patrimoine.id_commune.id_province),
        "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
        "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
    }
    return render(request, "patrimoine/patrimoine_form.html", context)


@login_required
@require_http_methods(["POST"])
def patrimoine_delete(request, id_patrimoine):
    """Delete patrimoine (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("patrimoine-list")

    patrimoine = get_object_or_404(Patrimoine, id_patrimoine=id_patrimoine)
    patrimoine.delete()
    return redirect("patrimoine-list")


@login_required
def patrimoine_map(request):
    """Interactive map for viewing/creating patrimoine."""
    patrimoines = Patrimoine.objects.all()
    context = {
        "patrimoines": patrimoines,
        "can_edit": _can_edit(request.user),
    }
    return render(request, "patrimoine/patrimoine_map.html", context)


@login_required
def api_provinces_by_region(request, id_region):
    """API endpoint: get provinces for a region."""
    provinces = Province.objects.filter(id_region=id_region).values("id_province", "nom_province")
    return JsonResponse(list(provinces), safe=False)


@login_required
def api_communes_by_province(request, id_province):
    """API endpoint: get communes for a province."""
    communes = Commune.objects.filter(id_province=id_province).values("id_commune", "nom_commune")
    return JsonResponse(list(communes), safe=False)


@login_required
def api_patrimoines_by_commune(request, id_commune):
    """API endpoint: get patrimoines for a commune."""
    patrimoines = Patrimoine.objects.filter(id_commune=id_commune).values("id_patrimoine", "nom_fr")
    return JsonResponse(list(patrimoines), safe=False)


@login_required
def api_regions(request):
    """API endpoint: get all regions."""
    regions = Region.objects.values("id_region", "nom_region")
    return JsonResponse(list(regions), safe=False)


# ====================== INSPECTIONS ======================
def _can_add_inspection(user):
    """Only INSPECTEUR can add inspections."""
    return user.groups.filter(name="INSPECTEUR").exists()


def _is_admin(user):
    """Check if user is Admin (can approve/reject modification requests)."""
    return user.is_superuser or user.groups.filter(name="ADMIN").exists()


@login_required
def inspection_list(request):
    """List inspections with pending modification requests for Admin."""
    inspections = Inspection.objects.select_related("id_patrimoine", "id_inspecteur").all()
    
    # Get pending modification requests for admins
    pending_requests = []
    if _is_admin(request.user):
        pending_requests = InspectionModificationRequest.objects.filter(
            status="PENDING"
        ).select_related("id_inspection__id_patrimoine", "requested_by")
    
    context = {
        "inspections": inspections,
        "pending_requests": pending_requests,
        "can_add": _can_add_inspection(request.user),
        "is_admin": _is_admin(request.user),
    }
    return render(request, "patrimoine/inspection_list.html", context)


@login_required
def inspection_detail(request, id_inspection):
    """View inspection details with modification history."""
    inspection = get_object_or_404(
        Inspection.objects.select_related("id_patrimoine", "id_inspecteur"),
        id_inspection=id_inspection
    )
    
    # Get all modification requests for this inspection
    modification_requests = inspection.modification_requests.select_related(
        "requested_by", "reviewed_by"
    ).order_by("-requested_at")
    
    # Check if inspecteur can request modification
    can_request_modification = (
        request.user.groups.filter(name="INSPECTEUR").exists() and
        inspection.id_inspecteur == request.user and
        not modification_requests.filter(status="PENDING").exists()  # No pending requests
    )
    
    context = {
        "inspection": inspection,
        "modification_requests": modification_requests,
        "can_request_modification": can_request_modification,
        "is_admin": _is_admin(request.user),
    }
    return render(request, "patrimoine/inspection_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def inspection_create(request):
    """Create inspection - only INSPECTEUR."""
    if not _can_add_inspection(request.user):
        return redirect("inspection-list")

    if request.method == "POST":
        try:
            id_patrimoine = request.POST.get("id_patrimoine", "").strip()
            date_inspection = request.POST.get("date_inspection", "").strip()
            etat = request.POST.get("etat", "").strip()
            observations = request.POST.get("observations", "").strip()

            patrimoine = Patrimoine.objects.get(id_patrimoine=id_patrimoine)
            Inspection.objects.create(
                id_patrimoine=patrimoine,
                id_inspecteur=request.user,
                date_inspection=date_inspection,
                etat=etat,
                observations=observations,
            )
            return redirect("inspection-list")
        except Exception as e:
            return render(request, "patrimoine/inspection_form.html", {"error": str(e)})

    context = {
        "regions": Region.objects.all(),
        "patrimoines": Patrimoine.objects.all(),
        "inspection_etat": Inspection.INSPECTION_ETAT,
    }
    return render(request, "patrimoine/inspection_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def inspection_request_edit(request, id_inspection):
    """Inspecteur requests modification for their inspection."""
    inspection = get_object_or_404(Inspection, id_inspection=id_inspection)
    
    # Only the inspecteur who created it can request modifications
    if inspection.id_inspecteur != request.user:
        return redirect("inspection-detail", id_inspection=id_inspection)
    
    # Check if there's already a pending request
    if inspection.modification_requests.filter(status="PENDING").exists():
        return redirect("inspection-detail", id_inspection=id_inspection)
    
    if request.method == "POST":
        try:
            # Collect proposed changes
            proposed_data = {
                "date_inspection": request.POST.get("date_inspection", "").strip(),
                "etat": request.POST.get("etat", "").strip(),
                "observations": request.POST.get("observations", "").strip(),
            }
            
            # Create modification request
            InspectionModificationRequest.objects.create(
                id_inspection=inspection,
                requested_by=request.user,
                proposed_data=proposed_data
            )
            
            return redirect("inspection-detail", id_inspection=id_inspection)
        except Exception as e:
            context = {
                "inspection": inspection,
                "inspection_etat": Inspection.INSPECTION_ETAT,
                "error": str(e)
            }
            return render(request, "patrimoine/inspection_edit_request.html", context)
    
    context = {
        "inspection": inspection,
        "inspection_etat": Inspection.INSPECTION_ETAT,
    }
    return render(request, "patrimoine/inspection_edit_request.html", context)


@login_required
@require_http_methods(["POST"])
def inspection_request_approve(request, id_request):
    """Admin approves modification request and applies changes."""
    if not _is_admin(request.user):
        return redirect("inspection-list")
    
    mod_request = get_object_or_404(InspectionModificationRequest, id_request=id_request)
    
    if mod_request.status != "PENDING":
        return redirect("inspection-list")
    
    try:
        # Apply proposed changes to inspection using raw SQL to avoid auto-updated_at trigger issues
        inspection = mod_request.id_inspection
        proposed = mod_request.proposed_data
        
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE inspection 
                   SET date_inspection = %s, etat = %s, observations = %s, updated_at = NOW()
                   WHERE id_inspection = %s""",
                [proposed['date_inspection'], proposed['etat'], proposed.get('observations', ''), inspection.id_inspection]
            )
        
        # Update request status
        mod_request.status = "APPROVED"
        mod_request.reviewed_by = request.user
        mod_request.reviewed_at = timezone.now()
        mod_request.admin_note = request.POST.get("admin_note", "").strip()
        mod_request.save()
        
        return redirect("inspection-detail", id_inspection=inspection.id_inspection)
    except Exception as e:
        return redirect("inspection-list")


@login_required
@require_http_methods(["POST"])
def inspection_request_reject(request, id_request):
    """Admin rejects modification request."""
    if not _is_admin(request.user):
        return redirect("inspection-list")
    
    mod_request = get_object_or_404(InspectionModificationRequest, id_request=id_request)
    
    if mod_request.status != "PENDING":
        return redirect("inspection-list")
    
    mod_request.status = "REJECTED"
    mod_request.reviewed_by = request.user
    mod_request.reviewed_at = timezone.now()
    mod_request.admin_note = request.POST.get("admin_note", "").strip()
    mod_request.save()
    
    return redirect("inspection-detail", id_inspection=mod_request.id_inspection.id_inspection)


# ====================== INTERVENTIONS ======================
@login_required
def intervention_list(request):
    """List interventions."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")
    interventions = Intervention.objects.select_related("id_patrimoine", "created_by").all()
    context = {"interventions": interventions}
    return render(request, "patrimoine/intervention_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def intervention_create(request):
    """Create intervention."""
    if not _can_edit(request.user):
        return redirect("intervention-list")

    if request.method == "POST":
        try:
            id_patrimoine = request.POST.get("id_patrimoine", "").strip()
            nom_projet = request.POST.get("nom_projet", "").strip()
            type_intervention = request.POST.get("type_intervention", "").strip()
            date_debut = request.POST.get("date_debut", "").strip()
            date_fin = request.POST.get("date_fin", "").strip()
            prestataire = request.POST.get("prestataire", "").strip()
            description = request.POST.get("description", "").strip()

            patrimoine = Patrimoine.objects.get(id_patrimoine=id_patrimoine)
            Intervention.objects.create(
                id_patrimoine=patrimoine,
                nom_projet=nom_projet,
                type_intervention=type_intervention,
                date_debut=date_debut,
                date_fin=date_fin or None,
                prestataire=prestataire,
                description=description,
                created_by=request.user,
            )
            return redirect("intervention-list")
        except Exception as e:
            return render(request, "patrimoine/intervention_form.html", {"error": str(e)})

    context = {
        "regions": Region.objects.all(),
        "patrimoines": Patrimoine.objects.all(),
        "intervention_types": Intervention.INTERVENTION_TYPES,
        "intervention_statuts": Intervention.INTERVENTION_STATUTS,
    }
    return render(request, "patrimoine/intervention_form.html", context)


# ====================== DOCUMENTS ======================
@login_required
def document_list(request):
    """List documents."""
    documents = Document.objects.select_related("uploaded_by").all()
    context = {"documents": documents, "can_add": _can_edit(request.user)}
    return render(request, "patrimoine/document_list.html", context)


# ====================== USERS MANAGEMENT (Superadmin) ======================
@login_required
def user_management(request):
    """User management page (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    users = User.objects.all().prefetch_related("groups")
    admin_group = Group.objects.get(name="ADMIN")
    inspecteur_group = Group.objects.get(name="INSPECTEUR")
    context = {"users": users, "admin_group": admin_group, "inspecteur_group": inspecteur_group}
    return render(request, "core/user_management.html", context)


@login_required
@require_http_methods(["POST"])
def toggle_user_group(request, user_id, group_name):
    """Toggle user group membership (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    user = get_object_or_404(User, id=user_id)
    group = get_object_or_404(Group, name=group_name)

    if user.groups.filter(name=group_name).exists():
        user.groups.remove(group)
    else:
        user.groups.add(group)

    return redirect("user-management")


# ====================== AUDIT LOG ======================
@login_required
def audit_log(request):
    """View audit log (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")
    return render(request, "core/audit_log.html")

