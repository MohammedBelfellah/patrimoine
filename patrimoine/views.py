import csv
import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
import logging

from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.contrib.gis.gdal import DataSource
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.files.storage import default_storage
from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_GET

from .models import AuditLog, Commune, Document, Inspection, InspectionModificationRequest, Intervention, Patrimoine, Province, Region


logger = logging.getLogger(__name__)


def _geometry_from_spatial_file(uploaded_file):
    """Extract polygon geometry from uploaded KML or Shapefile zip."""
    filename = uploaded_file.name.lower()
    if not (filename.endswith(".kml") or filename.endswith(".zip")):
        raise ValueError("Formats acceptes: .kml ou .zip (shapefile)")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, uploaded_file.name)
        with open(file_path, "wb") as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        ds_path = file_path
        if filename.endswith(".zip"):
            ds_path = f"/vsizip/{file_path}"

        ds = DataSource(ds_path)
        if len(ds) == 0:
            raise ValueError("Fichier spatial vide ou illisible")

        layer = ds[0]
        if len(layer) == 0:
            raise ValueError("Aucune geometrie dans le fichier")

        g = None
        for feature in layer:
            if not feature.geom:
                continue
            candidate = GEOSGeometry(feature.geom.geojson)
            if candidate.geom_type == "Polygon":
                g = MultiPolygon(candidate)
                break
            if candidate.geom_type == "MultiPolygon":
                g = candidate
                break

        if g is None:
            raise ValueError("Le fichier doit contenir au moins un polygone")

        if g.geom_type == "Polygon":
            g = MultiPolygon(g)
        elif g.geom_type != "MultiPolygon":
            raise ValueError("Le fichier doit contenir un polygone")

        return g


def _can_edit(user):
    """Check if user can edit patrimoine (admin/editeur)."""
    return user.is_superuser or user.groups.filter(name="ADMIN").exists()


def _can_view(user):
    """Check if user can view patrimoine (all authenticated users)."""
    return user.is_authenticated


def _normalize_audit_data(data):
    if not data:
        return None
    normalized = {}
    for key, value in data.items():
        if isinstance(value, (datetime, date)):
            normalized[key] = value.isoformat()
        elif isinstance(value, Decimal):
            normalized[key] = float(value)
        else:
            normalized[key] = value
    return normalized


def _log_audit(actor, action, entity_type, entity_id, old_data=None, new_data=None):
    AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_data=_normalize_audit_data(old_data),
        new_data=_normalize_audit_data(new_data),
        created_at=timezone.now(),
    )


def _dashboard_url_for_role(role):
    if role == "ADMIN":
        return reverse("dashboard-admin")
    if role == "INSPECTEUR":
        return reverse("dashboard-inspecteur")
    return reverse("dashboard-public")


def _send_welcome_user_email(request, user, raw_password, role):
    login_url = request.build_absolute_uri(reverse("login"))
    dashboard_url = request.build_absolute_uri(_dashboard_url_for_role(role))
    role_label = role.capitalize()

    subject = "Bienvenue sur Patrimoine"
    text_message = f"""
Bonjour {user.username},

Votre compte a été créé avec succès sur la plateforme Patrimoine.

Rôle : {role_label}
Email : {user.email}
Nom d'utilisateur : {user.username}
Mot de passe provisoire : {raw_password}

Accédez à votre espace : {dashboard_url}
Connexion : {login_url}

Merci,
L’équipe Patrimoine
"""
    html_message = f"""
<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto;'>
  <h2 style='color:#2563eb;'>Bienvenue sur <span style='color:#0f172a;'>Patrimoine</span></h2>
  <p>Bonjour <b>{user.username}</b>,</p>
  <p>Votre compte a été créé avec succès sur la plateforme <b>Patrimoine</b>.</p>
  <ul style='background:#f1f5f9;padding:14px 18px;border-radius:8px;'>
    <li><b>Rôle :</b> {role_label}</li>
    <li><b>Email :</b> {user.email}</li>
    <li><b>Nom d'utilisateur :</b> {user.username}</li>
    <li><b>Mot de passe provisoire :</b> <span style='color:#dc2626;'>{raw_password}</span></li>
  </ul>
  <p>Accédez à votre espace : <a href='{dashboard_url}' style='color:#2563eb;'>Tableau de bord</a></p>
  <p>Connexion : <a href='{login_url}' style='color:#2563eb;'>{login_url}</a></p>
  <p style='margin-top:18px;font-size:13px;color:#64748b;'>Merci,<br>L’équipe Patrimoine</p>
</div>
"""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html_message, "text/html")
    msg.send(fail_silently=False)


def _send_user_updated_email(request, user, old_email, old_username, role, raw_password=None):
    login_url = request.build_absolute_uri(reverse("login"))
    dashboard_url = request.build_absolute_uri(_dashboard_url_for_role(role))
    role_label = role.capitalize()

    subject = "Mise à jour de votre compte Patrimoine"
    text_message = f"""
Bonjour {user.username},

Votre compte Patrimoine a été mis à jour par le Superadmin.

Nouveau rôle : {role_label}
Email : {user.email}
Nom d'utilisateur : {user.username}
"""
    if raw_password:
        text_message += f"\nNouveau mot de passe provisoire : {raw_password}\n(Changez-le après connexion.)\n"
    if old_email != user.email or old_username != user.username:
        text_message += f"\nAnciennes informations :\n- Ancien email : {old_email}\n- Ancien nom d'utilisateur : {old_username}\n"
    text_message += f"\nConnexion : {login_url}\nTableau de bord : {dashboard_url}\n\nMerci,\nL’équipe Patrimoine"

    html_message = f"""
<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto;'>
  <h2 style='color:#2563eb;'>Mise à jour de votre <span style='color:#0f172a;'>compte Patrimoine</span></h2>
  <p>Bonjour <b>{user.username}</b>,</p>
  <p>Votre compte a été mis à jour par le Superadmin.</p>
  <ul style='background:#f1f5f9;padding:14px 18px;border-radius:8px;'>
    <li><b>Nouveau rôle :</b> {role_label}</li>
    <li><b>Email :</b> {user.email}</li>
    <li><b>Nom d'utilisateur :</b> {user.username}</li>
    {f"<li><b>Nouveau mot de passe provisoire :</b> <span style='color:#dc2626;'>{raw_password}</span></li>" if raw_password else ""}
  </ul>
  {f"<p style='font-size:13px;color:#64748b;'>Ancien email : {old_email}<br>Ancien nom d'utilisateur : {old_username}</p>" if (old_email != user.email or old_username != user.username) else ""}
  <p>Connexion : <a href='{login_url}' style='color:#2563eb;'>{login_url}</a></p>
  <p>Tableau de bord : <a href='{dashboard_url}' style='color:#2563eb;'>{dashboard_url}</a></p>
  <p style='margin-top:18px;font-size:13px;color:#64748b;'>Merci,<br>L’équipe Patrimoine</p>
</div>
"""
    recipients = [user.email]
    if old_email and old_email != user.email:
        recipients.append(old_email)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    msg.attach_alternative(html_message, "text/html")
    msg.send(fail_silently=False)


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
def patrimoine_export(request):
    """Export patrimoines to CSV."""
    if not _can_view(request.user):
        return redirect("public-map")

    # Apply same filters as list view
    patrimoines = Patrimoine.objects.select_related("id_commune__id_province__id_region").all()
    
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
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="patrimoines_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    response.write('\ufeff')  # UTF-8 BOM for Excel
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Nom FR', 'Nom AR', 'Type', 'Statut', 'Référence Administrative',
        'Description', 'Région', 'Province', 'Commune', 
        'Créé le', 'Modifié le'
    ])
    
    for p in patrimoines:
        writer.writerow([
            p.id_patrimoine,
            p.nom_fr,
            p.nom_ar or '',
            p.get_type_patrimoine_display(),
            p.get_statut_display(),
            p.reference_administrative or '',
            p.description or '',
            p.id_commune.id_province.id_region.nom_region,
            p.id_commune.id_province.nom_province,
            p.id_commune.nom_commune,
            p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else '',
            p.updated_at.strftime('%Y-%m-%d %H:%M:%S') if p.updated_at else '',
        ])
    
    return response


@login_required
def patrimoine_detail(request, id_patrimoine):
    """Display patrimoine details with uploaded images."""
    if not _can_view(request.user):
        return redirect("public-map")

    patrimoine = get_object_or_404(Patrimoine, id_patrimoine=id_patrimoine)
    images = Document.objects.filter(id_patrimoine=patrimoine, type_document="IMAGE").order_by("uploaded_at")
    
    context = {
        "patrimoine": patrimoine,
        "images": images,
        "can_edit": _can_edit(request.user),
    }
    return render(request, "patrimoine/patrimoine_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def patrimoine_create(request):
    """Create new patrimoine with optional image uploads (max 5 images, 5MB each)."""
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
            spatial_file = request.FILES.get("spatial_file")
            id_commune = request.POST.get("id_commune", "").strip()

            if not all([nom_fr, type_patrimoine, id_commune]) or (not geojson_str and not spatial_file):
                messages.error(request, "Champs obligatoires manquants (Nom, Type, Commune, Polygone)")
                context = {
                    "regions": Region.objects.all(),
                    "provinces": Province.objects.all(),
                    "communes": Commune.objects.all(),
                    "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
                    "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
                }
                return render(request, "patrimoine/patrimoine_form.html", context)

            # Validate uploaded files
            uploaded_files = request.FILES.getlist("images")
            if len(uploaded_files) > 5:
                raise ValueError("Maximum 5 images autorisées")
            
            MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
            ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            
            for uploaded_file in uploaded_files:
                if uploaded_file.size > MAX_FILE_SIZE:
                    raise ValueError(f"L'image '{uploaded_file.name}' dépasse 5MB")
                
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext not in ALLOWED_EXTENSIONS:
                    raise ValueError(f"Format non autorisé pour '{uploaded_file.name}'. Formats acceptés: JPG, PNG, GIF, WEBP")

            commune = Commune.objects.get(id_commune=id_commune)
            if spatial_file:
                polygon_geom = _geometry_from_spatial_file(spatial_file)
            else:
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

            # Save uploaded images to Document table
            for uploaded_file in uploaded_files:
                # Create directory structure: patrimoine/{patrimoine_id}/
                file_path = f"patrimoine/{patrimoine_id}/{uploaded_file.name}"
                saved_path = default_storage.save(file_path, uploaded_file)
                
                # Calculate file size in MB
                file_size_mb = Decimal(uploaded_file.size) / Decimal(1024 * 1024)
                
                # Create Document record
                document = Document.objects.create(
                    type_document="IMAGE",
                    file_name=uploaded_file.name,
                    file_path=saved_path,
                    file_size_mb=round(file_size_mb, 2),
                    uploaded_by=request.user,
                    id_patrimoine_id=patrimoine_id,
                )
                _log_audit(
                    request.user,
                    "CREATE",
                    "DOCUMENT",
                    document.id_document,
                    new_data={
                        "type_document": document.type_document,
                        "file_name": document.file_name,
                        "file_size_mb": document.file_size_mb,
                        "id_patrimoine": document.id_patrimoine_id,
                    },
                )

            _log_audit(
                request.user,
                "CREATE",
                "PATRIMOINE",
                patrimoine_id,
                new_data={
                    "nom_fr": nom_fr,
                    "nom_ar": nom_ar or None,
                    "type_patrimoine": type_patrimoine,
                    "statut": statut,
                    "reference_administrative": reference_administrative or None,
                    "id_commune": id_commune,
                },
            )

            messages.success(request, "Patrimoine créé avec succès")
            return redirect("patrimoine-detail", id_patrimoine=patrimoine_id)
        except Exception as e:
            messages.error(request, str(e))
            context = {
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
    """Edit existing patrimoine with optional image uploads (max 5 total images)."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")

    patrimoine = get_object_or_404(Patrimoine, id_patrimoine=id_patrimoine)

    if request.method == "POST":
        try:
            old_data = {
                "nom_fr": patrimoine.nom_fr,
                "nom_ar": patrimoine.nom_ar,
                "description": patrimoine.description,
                "type_patrimoine": patrimoine.type_patrimoine,
                "statut": patrimoine.statut,
                "reference_administrative": patrimoine.reference_administrative,
                "id_commune": patrimoine.id_commune.id_commune,
            }
            nom_fr = request.POST.get("nom_fr", patrimoine.nom_fr).strip()
            nom_ar = request.POST.get("nom_ar", patrimoine.nom_ar or "").strip()
            description = request.POST.get("description", patrimoine.description or "").strip()
            type_patrimoine = request.POST.get("type_patrimoine", patrimoine.type_patrimoine).strip()
            statut = request.POST.get("statut", patrimoine.statut).strip()
            reference_administrative = request.POST.get("reference_administrative", patrimoine.reference_administrative or "").strip()
            geojson_str = request.POST.get("geojson", "").strip()
            id_commune = request.POST.get("id_commune", "").strip()

            # Validate uploaded files
            uploaded_files = request.FILES.getlist("images")
            current_images_count = Document.objects.filter(id_patrimoine=patrimoine, type_document="IMAGE").count()
            
            if current_images_count + len(uploaded_files) > 5:
                raise ValueError(f"Maximum 5 images au total. Actuellement: {current_images_count}, tentative d'ajout: {len(uploaded_files)}")
            
            MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
            ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            
            for uploaded_file in uploaded_files:
                if uploaded_file.size > MAX_FILE_SIZE:
                    raise ValueError(f"L'image '{uploaded_file.name}' dépasse 5MB")
                
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext not in ALLOWED_EXTENSIONS:
                    raise ValueError(f"Format non autorisé pour '{uploaded_file.name}'. Formats acceptés: JPG, PNG, GIF, WEBP")

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

            # Save uploaded images to Document table
            for uploaded_file in uploaded_files:
                # Create directory structure: patrimoine/{patrimoine_id}/
                file_path = f"patrimoine/{patrimoine.id_patrimoine}/{uploaded_file.name}"
                saved_path = default_storage.save(file_path, uploaded_file)
                
                # Calculate file size in MB
                file_size_mb = Decimal(uploaded_file.size) / Decimal(1024 * 1024)
                
                # Create Document record
                document = Document.objects.create(
                    type_document="IMAGE",
                    file_name=uploaded_file.name,
                    file_path=saved_path,
                    file_size_mb=round(file_size_mb, 2),
                    uploaded_by=request.user,
                    id_patrimoine=patrimoine,
                )
                _log_audit(
                    request.user,
                    "CREATE",
                    "DOCUMENT",
                    document.id_document,
                    new_data={
                        "type_document": document.type_document,
                        "file_name": document.file_name,
                        "file_size_mb": document.file_size_mb,
                        "id_patrimoine": patrimoine.id_patrimoine,
                    },
                )

            _log_audit(
                request.user,
                "UPDATE",
                "PATRIMOINE",
                patrimoine.id_patrimoine,
                old_data=old_data,
                new_data={
                    "nom_fr": nom_fr,
                    "nom_ar": nom_ar or None,
                    "description": description or None,
                    "type_patrimoine": type_patrimoine,
                    "statut": statut,
                    "reference_administrative": reference_administrative or None,
                    "id_commune": id_commune or patrimoine.id_commune.id_commune,
                },
            )

            messages.success(request, "Patrimoine mis à jour avec succès")
            return redirect("patrimoine-detail", id_patrimoine=patrimoine.id_patrimoine)
        except Exception as e:
            messages.error(request, str(e))
            current_images = Document.objects.filter(id_patrimoine=patrimoine, type_document="IMAGE").order_by("uploaded_at")
            context = {
                "patrimoine": patrimoine,
                "current_images": current_images,
                "patrimoine_geojson": json.dumps(json.loads(patrimoine.polygon_geom.geojson)) if patrimoine.polygon_geom else "null",
                "regions": Region.objects.all(),
                "provinces": Province.objects.filter(id_region=patrimoine.id_commune.id_province.id_region),
                "communes": Commune.objects.filter(id_province=patrimoine.id_commune.id_province),
                "patrimoine_types": Patrimoine.PATRIMOINE_TYPES,
                "patrimoine_statuts": Patrimoine.PATRIMOINE_STATUTS,
            }
            return render(request, "patrimoine/patrimoine_form.html", context)

    current_images = Document.objects.filter(id_patrimoine=patrimoine, type_document="IMAGE").order_by("uploaded_at")
    context = {
        "patrimoine": patrimoine,
        "current_images": current_images,
        "patrimoine_geojson": json.dumps(json.loads(patrimoine.polygon_geom.geojson)) if patrimoine.polygon_geom else "null",
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
    old_data = {
        "nom_fr": patrimoine.nom_fr,
        "nom_ar": patrimoine.nom_ar,
        "description": patrimoine.description,
        "type_patrimoine": patrimoine.type_patrimoine,
        "statut": patrimoine.statut,
        "reference_administrative": patrimoine.reference_administrative,
        "id_commune": patrimoine.id_commune.id_commune,
    }
    patrimoine.delete()
    _log_audit(request.user, "DELETE", "PATRIMOINE", id_patrimoine, old_data=old_data)
    return redirect("patrimoine-list")


@login_required
def patrimoine_map(request):
    """Interactive map for viewing/creating patrimoine."""
    patrimoines = Patrimoine.objects.select_related(
        "id_commune__id_province__id_region"
    ).all()

    data = []
    for p in patrimoines:
        geom = json.loads(p.polygon_geom.geojson) if p.polygon_geom else None
        data.append(
            {
                "id": p.id_patrimoine,
                "nom": p.nom_fr,
                "type": p.type_patrimoine,
                "geom": geom,
            }
        )

    context = {
        "patrimoines": patrimoines,
        "patrimoines_json": json.dumps(data),
        "can_edit": _can_edit(request.user),
    }
    return render(request, "patrimoine/patrimoine_map.html", context)




@csrf_exempt
@require_GET
def api_provinces_by_region(request, id_region):
    """API endpoint: get provinces for a region."""
    provinces = Province.objects.filter(id_region=id_region).values("id_province", "nom_province")
    return JsonResponse(list(provinces), safe=False)


@csrf_exempt
@require_GET
def api_communes_by_province(request, id_province):
    """API endpoint: get communes for a province."""
    communes = Commune.objects.filter(id_province=id_province).values("id_commune", "nom_commune")
    return JsonResponse(list(communes), safe=False)


@login_required
def api_patrimoines_by_commune(request, id_commune):
    """API endpoint: get patrimoines for a commune."""
    patrimoines = Patrimoine.objects.filter(id_commune=id_commune).values("id_patrimoine", "nom_fr")
    return JsonResponse(list(patrimoines), safe=False)


@csrf_exempt
@require_GET
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

    search = request.GET.get("search", "").strip()
    etat_filter = request.GET.get("etat", "").strip()
    inspecteur_filter = request.GET.get("inspecteur", "").strip()
    patrimoine_filter = request.GET.get("patrimoine", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if search:
        inspections = inspections.filter(
            Q(id_patrimoine__nom_fr__icontains=search)
            | Q(id_inspecteur__email__icontains=search)
        )
    if etat_filter:
        inspections = inspections.filter(etat=etat_filter)
    if inspecteur_filter:
        inspections = inspections.filter(id_inspecteur__id=inspecteur_filter)
    if patrimoine_filter:
        inspections = inspections.filter(id_patrimoine__id_patrimoine=patrimoine_filter)
    if date_from:
        inspections = inspections.filter(date_inspection__gte=date_from)
    if date_to:
        inspections = inspections.filter(date_inspection__lte=date_to)
    
    # Get pending modification requests for admins
    pending_requests = []
    if _is_admin(request.user):
        pending_requests = InspectionModificationRequest.objects.filter(
            status="PENDING"
        ).select_related("id_inspection__id_patrimoine", "requested_by")
    
    inspecteurs = User.objects.filter(groups__name="INSPECTEUR").order_by("email").distinct()
    patrimoines = Patrimoine.objects.only("id_patrimoine", "nom_fr").order_by("nom_fr")

    etat_options = [
        {"value": code, "label": label, "selected": code == etat_filter}
        for code, label in Inspection.INSPECTION_ETAT
    ]
    inspecteur_options = [
        {"id": insp.id, "email": insp.email, "selected": str(insp.id) == inspecteur_filter}
        for insp in inspecteurs
    ]
    patrimoine_options = [
        {
            "id": pat.id_patrimoine,
            "nom_fr": pat.nom_fr,
            "selected": str(pat.id_patrimoine) == patrimoine_filter,
        }
        for pat in patrimoines
    ]

    context = {
        "inspections": inspections,
        "pending_requests": pending_requests,
        "can_add": _can_add_inspection(request.user),
        "is_admin": _is_admin(request.user),
        "etat_options": etat_options,
        "inspecteur_options": inspecteur_options,
        "patrimoine_options": patrimoine_options,
    }
    return render(request, "patrimoine/inspection_list.html", context)


@login_required
def inspection_export(request):
    """Export inspections to CSV."""
    inspections = Inspection.objects.select_related("id_patrimoine", "id_inspecteur").all()
    
    # Apply same filters as list view
    search = request.GET.get("search", "").strip()
    etat_filter = request.GET.get("etat", "").strip()
    inspecteur_filter = request.GET.get("inspecteur", "").strip()
    patrimoine_filter = request.GET.get("patrimoine", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    
    if search:
        inspections = inspections.filter(
            Q(id_patrimoine__nom_fr__icontains=search)
            | Q(id_inspecteur__email__icontains=search)
        )
    if etat_filter:
        inspections = inspections.filter(etat=etat_filter)
    if inspecteur_filter:
        inspections = inspections.filter(id_inspecteur__id=inspecteur_filter)
    if patrimoine_filter:
        inspections = inspections.filter(id_patrimoine__id_patrimoine=patrimoine_filter)
    if date_from:
        inspections = inspections.filter(date_inspection__gte=date_from)
    if date_to:
        inspections = inspections.filter(date_inspection__lte=date_to)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="inspections_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    response.write('\ufeff')  # UTF-8 BOM for Excel
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Patrimoine', 'Inspecteur', 'Date Inspection', 'État', 
        'Observations', 'Créé le', 'Modifié le'
    ])
    
    for i in inspections:
        writer.writerow([
            i.id_inspection,
            i.id_patrimoine.nom_fr,
            i.id_inspecteur.email if i.id_inspecteur else '',
            i.date_inspection.strftime('%Y-%m-%d') if i.date_inspection else '',
            i.get_etat_display(),
            i.observations or '',
            i.created_at.strftime('%Y-%m-%d %H:%M:%S') if i.created_at else '',
            i.updated_at.strftime('%Y-%m-%d %H:%M:%S') if i.updated_at else '',
        ])
    
    return response


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
    
    # Get documents linked to this inspection
    documents = Document.objects.filter(id_inspection=inspection)
    context = {
        "inspection": inspection,
        "modification_requests": modification_requests,
        "can_request_modification": can_request_modification,
        "is_admin": _is_admin(request.user),
        "documents": documents,
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
            inspection = Inspection.objects.create(
                id_patrimoine=patrimoine,
                id_inspecteur=request.user,
                date_inspection=date_inspection,
                etat=etat,
                observations=observations,
            )
            # Handle file uploads (PDF, images, etc.)
            files = request.FILES.getlist("files")
            for f in files:
                ext = f.name.split('.')[-1].lower()
                doc_type = "PDF" if ext == "pdf" else ("IMAGE" if ext in ["jpg", "jpeg", "png", "gif", "webp"] else "AUTRE")
                file_path = default_storage.save(f"patrimoine/inspection/{inspection.id_inspection}/{f.name}", f)
                Document.objects.create(
                    type_document=doc_type,
                    file_name=f.name,
                    file_path=file_path,
                    file_size_mb=round(f.size / (1024 * 1024), 2),
                    uploaded_by=request.user,
                    id_inspection=inspection,
                )
            _log_audit(
                request.user,
                "CREATE",
                "INSPECTION",
                inspection.id_inspection,
                new_data={
                    "id_patrimoine": patrimoine.id_patrimoine,
                    "date_inspection": inspection.date_inspection,
                    "etat": inspection.etat,
                    "observations": inspection.observations,
                },
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
        old_data = {
            "date_inspection": inspection.date_inspection,
            "etat": inspection.etat,
            "observations": inspection.observations,
        }
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

        _log_audit(
            request.user,
            "REQUEST_APPROVE",
            "INSPECTION_REQUEST",
            mod_request.id_request,
            new_data={
                "status": mod_request.status,
                "admin_note": mod_request.admin_note,
            },
        )
        _log_audit(
            request.user,
            "UPDATE",
            "INSPECTION",
            inspection.id_inspection,
            old_data=old_data,
            new_data={
                "date_inspection": proposed.get("date_inspection"),
                "etat": proposed.get("etat"),
                "observations": proposed.get("observations"),
            },
        )
        
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

    _log_audit(
        request.user,
        "REQUEST_REJECT",
        "INSPECTION_REQUEST",
        mod_request.id_request,
        new_data={
            "status": mod_request.status,
            "admin_note": mod_request.admin_note,
        },
    )
    
    return redirect("inspection-detail", id_inspection=mod_request.id_inspection.id_inspection)


# ====================== INTERVENTIONS ======================
@login_required
def intervention_list(request):
    """List interventions."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")
    interventions = Intervention.objects.select_related("id_patrimoine", "created_by").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    type_filter = request.GET.get("type", "").strip()
    statut_filter = request.GET.get("statut", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if search:
        interventions = interventions.filter(
            Q(nom_projet__icontains=search)
            | Q(id_patrimoine__nom_fr__icontains=search)
            | Q(prestataire__icontains=search)
        )
    if type_filter:
        interventions = interventions.filter(type_intervention=type_filter)
    if statut_filter:
        interventions = interventions.filter(statut=statut_filter)
    if date_from:
        interventions = interventions.filter(date_debut__gte=date_from)
    if date_to:
        interventions = interventions.filter(date_debut__lte=date_to)

    context = {
        "interventions": interventions,
        "intervention_types": Intervention.INTERVENTION_TYPES,
        "intervention_statuts": Intervention.INTERVENTION_STATUTS,
    }
    return render(request, "patrimoine/intervention_list.html", context)


@login_required
def intervention_export(request):
    """Export interventions to CSV."""
    if not _can_edit(request.user):
        return redirect("patrimoine-list")
    
    interventions = Intervention.objects.select_related("id_patrimoine", "created_by").order_by("-created_at")
    
    # Apply same filters as list view
    search = request.GET.get("search", "").strip()
    type_filter = request.GET.get("type", "").strip()
    statut_filter = request.GET.get("statut", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    
    if search:
        interventions = interventions.filter(
            Q(nom_projet__icontains=search)
            | Q(id_patrimoine__nom_fr__icontains=search)
            | Q(prestataire__icontains=search)
        )
    if type_filter:
        interventions = interventions.filter(type_intervention=type_filter)
    if statut_filter:
        interventions = interventions.filter(statut=statut_filter)
    if date_from:
        interventions = interventions.filter(date_debut__gte=date_from)
    if date_to:
        interventions = interventions.filter(date_debut__lte=date_to)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="interventions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    response.write('\ufeff')  # UTF-8 BOM for Excel
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Patrimoine', 'Nom Projet', 'Type', 'Statut', 'Date Début', 
        'Date Fin', 'Prestataire', 'Description', 'Créé par', 
        'Créé le', 'Modifié le'
    ])
    
    for i in interventions:
        writer.writerow([
            i.id_intervention,
            i.id_patrimoine.nom_fr,
            i.nom_projet,
            i.get_type_intervention_display(),
            i.get_statut_display(),
            i.date_debut.strftime('%Y-%m-%d') if i.date_debut else '',
            i.date_fin.strftime('%Y-%m-%d') if i.date_fin else '',
            i.prestataire or '',
            i.description or '',
            i.created_by.email if i.created_by else '',
            i.created_at.strftime('%Y-%m-%d %H:%M:%S') if i.created_at else '',
            i.updated_at.strftime('%Y-%m-%d %H:%M:%S') if i.updated_at else '',
        ])
    
    return response


@login_required
def intervention_detail(request, id_intervention):
    """Show intervention details."""
    if not _can_edit(request.user):
        return redirect("intervention-list")

    intervention = get_object_or_404(
        Intervention.objects.select_related("id_patrimoine", "created_by"),
        id_intervention=id_intervention,
    )
    context = {"intervention": intervention}
    return render(request, "patrimoine/intervention_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def intervention_create(request):
    """Create intervention."""
    if not _can_edit(request.user):
        return redirect("intervention-list")

    if request.method == "POST":
        form_data = {
            "id_region": request.POST.get("id_region", "").strip(),
            "id_province": request.POST.get("id_province", "").strip(),
            "id_commune": request.POST.get("id_commune", "").strip(),
            "id_patrimoine": request.POST.get("id_patrimoine", "").strip(),
            "nom_projet": request.POST.get("nom_projet", "").strip(),
            "type_intervention": request.POST.get("type_intervention", "").strip(),
            "date_debut": request.POST.get("date_debut", "").strip(),
            "date_fin": request.POST.get("date_fin", "").strip(),
            "prestataire": request.POST.get("prestataire", "").strip(),
            "description": request.POST.get("description", "").strip(),
        }
        try:
            id_patrimoine = form_data["id_patrimoine"]
            nom_projet = form_data["nom_projet"]
            type_intervention = form_data["type_intervention"]
            statut = request.POST.get("statut", "PLANIFIEE").strip() or "PLANIFIEE"
            date_debut = form_data["date_debut"]
            date_fin = form_data["date_fin"]
            prestataire = form_data["prestataire"]
            description = form_data["description"]

            if not id_patrimoine:
                raise ValueError("Veuillez sélectionner un patrimoine")
            if not nom_projet or not type_intervention or not date_debut:
                raise ValueError("Champs obligatoires manquants")

            patrimoine = Patrimoine.objects.get(id_patrimoine=id_patrimoine)
            intervention = Intervention.objects.create(
                id_patrimoine=patrimoine,
                nom_projet=nom_projet,
                type_intervention=type_intervention,
                date_debut=date_debut,
                date_fin=date_fin or None,
                prestataire=prestataire,
                description=description,
                statut=statut,
                created_by=request.user,
            )
            _log_audit(
                request.user,
                "CREATE",
                "INTERVENTION",
                intervention.id_intervention,
                new_data={
                    "id_patrimoine": patrimoine.id_patrimoine,
                    "nom_projet": intervention.nom_projet,
                    "type_intervention": intervention.type_intervention,
                    "statut": intervention.statut,
                    "date_debut": intervention.date_debut,
                    "date_fin": intervention.date_fin,
                    "prestataire": intervention.prestataire,
                },
            )
            messages.success(request, "Intervention créée avec succès")
            return redirect("intervention-list")
        except Exception as e:
            messages.error(request, str(e))
            context = {
                "regions": Region.objects.all(),
                "patrimoines": Patrimoine.objects.select_related("id_commune").all(),
                "intervention_types": Intervention.INTERVENTION_TYPES,
                "intervention_statuts": Intervention.INTERVENTION_STATUTS,
                "form_data": form_data,
                "is_edit": False,
            }
            return render(request, "patrimoine/intervention_form.html", context)

    context = {
        "regions": Region.objects.all(),
        "patrimoines": Patrimoine.objects.select_related("id_commune").all(),
        "intervention_types": Intervention.INTERVENTION_TYPES,
        "intervention_statuts": Intervention.INTERVENTION_STATUTS,
        "form_data": {},
        "is_edit": False,
    }
    return render(request, "patrimoine/intervention_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def intervention_edit(request, id_intervention):
    """Edit intervention."""
    if not _can_edit(request.user):
        return redirect("intervention-list")

    intervention = get_object_or_404(Intervention, id_intervention=id_intervention)

    if request.method == "POST":
        old_data = {
            "id_patrimoine": intervention.id_patrimoine.id_patrimoine,
            "nom_projet": intervention.nom_projet,
            "type_intervention": intervention.type_intervention,
            "statut": intervention.statut,
            "date_debut": intervention.date_debut,
            "date_fin": intervention.date_fin,
            "prestataire": intervention.prestataire,
            "description": intervention.description,
        }
        form_data = {
            "id_region": request.POST.get("id_region", "").strip(),
            "id_province": request.POST.get("id_province", "").strip(),
            "id_commune": request.POST.get("id_commune", "").strip(),
            "id_patrimoine": request.POST.get("id_patrimoine", "").strip(),
            "nom_projet": request.POST.get("nom_projet", "").strip(),
            "type_intervention": request.POST.get("type_intervention", "").strip(),
            "statut": request.POST.get("statut", intervention.statut).strip(),
            "date_debut": request.POST.get("date_debut", "").strip(),
            "date_fin": request.POST.get("date_fin", "").strip(),
            "prestataire": request.POST.get("prestataire", "").strip(),
            "description": request.POST.get("description", "").strip(),
        }
        try:
            if not form_data["id_patrimoine"]:
                raise ValueError("Veuillez sélectionner un patrimoine")
            if not form_data["nom_projet"] or not form_data["type_intervention"] or not form_data["date_debut"]:
                raise ValueError("Champs obligatoires manquants")

            patrimoine = Patrimoine.objects.get(id_patrimoine=form_data["id_patrimoine"])
            intervention.id_patrimoine = patrimoine
            intervention.nom_projet = form_data["nom_projet"]
            intervention.type_intervention = form_data["type_intervention"]
            intervention.statut = form_data["statut"]
            intervention.date_debut = form_data["date_debut"]
            intervention.date_fin = form_data["date_fin"] or None
            intervention.prestataire = form_data["prestataire"]
            intervention.description = form_data["description"]
            intervention.save()

            _log_audit(
                request.user,
                "UPDATE",
                "INTERVENTION",
                intervention.id_intervention,
                old_data=old_data,
                new_data={
                    "id_patrimoine": intervention.id_patrimoine.id_patrimoine,
                    "nom_projet": intervention.nom_projet,
                    "type_intervention": intervention.type_intervention,
                    "statut": intervention.statut,
                    "date_debut": intervention.date_debut,
                    "date_fin": intervention.date_fin,
                    "prestataire": intervention.prestataire,
                    "description": intervention.description,
                },
            )

            messages.success(request, "Intervention mise à jour avec succès")
            return redirect("intervention-detail", id_intervention=intervention.id_intervention)
        except Exception as e:
            messages.error(request, str(e))
            context = {
                "intervention": intervention,
                "regions": Region.objects.all(),
                "patrimoines": Patrimoine.objects.select_related("id_commune").all(),
                "intervention_types": Intervention.INTERVENTION_TYPES,
                "intervention_statuts": Intervention.INTERVENTION_STATUTS,
                "form_data": form_data,
                "is_edit": True,
            }
            return render(request, "patrimoine/intervention_form.html", context)

    form_data = {
        "id_region": str(intervention.id_patrimoine.id_commune.id_province.id_region.id_region),
        "id_province": str(intervention.id_patrimoine.id_commune.id_province.id_province),
        "id_commune": str(intervention.id_patrimoine.id_commune.id_commune),
        "id_patrimoine": str(intervention.id_patrimoine.id_patrimoine),
        "nom_projet": intervention.nom_projet,
        "type_intervention": intervention.type_intervention,
        "statut": intervention.statut,
        "date_debut": intervention.date_debut.isoformat() if intervention.date_debut else "",
        "date_fin": intervention.date_fin.isoformat() if intervention.date_fin else "",
        "prestataire": intervention.prestataire or "",
        "description": intervention.description or "",
    }
    context = {
        "intervention": intervention,
        "regions": Region.objects.all(),
        "patrimoines": Patrimoine.objects.select_related("id_commune").all(),
        "intervention_types": Intervention.INTERVENTION_TYPES,
        "intervention_statuts": Intervention.INTERVENTION_STATUTS,
        "form_data": form_data,
        "is_edit": True,
    }
    return render(request, "patrimoine/intervention_form.html", context)


@login_required
@require_http_methods(["POST"])
def intervention_delete(request, id_intervention):
    """Delete intervention."""
    if not _can_edit(request.user):
        return redirect("intervention-list")

    intervention = get_object_or_404(Intervention, id_intervention=id_intervention)
    old_data = {
        "id_patrimoine": intervention.id_patrimoine.id_patrimoine,
        "nom_projet": intervention.nom_projet,
        "type_intervention": intervention.type_intervention,
        "statut": intervention.statut,
        "date_debut": intervention.date_debut,
        "date_fin": intervention.date_fin,
        "prestataire": intervention.prestataire,
        "description": intervention.description,
    }
    intervention.delete()
    _log_audit(request.user, "DELETE", "INTERVENTION", id_intervention, old_data=old_data)
    messages.success(request, "Intervention supprimée avec succès")
    return redirect("intervention-list")


# ====================== DOCUMENTS ======================
@login_required
def document_list(request):
    """List documents."""
    documents = Document.objects.select_related("uploaded_by").all()

    search = request.GET.get("search", "").strip()
    type_filter = request.GET.get("type", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if search:
        documents = documents.filter(
            Q(file_name__icontains=search)
            | Q(uploaded_by__email__icontains=search)
        )
    if type_filter:
        documents = documents.filter(type_document=type_filter)
    if date_from:
        documents = documents.filter(uploaded_at__date__gte=date_from)
    if date_to:
        documents = documents.filter(uploaded_at__date__lte=date_to)

    context = {
        "documents": documents,
        "can_add": _can_edit(request.user),
        "document_types": Document.DOCUMENT_TYPES,
    }
    return render(request, "patrimoine/document_list.html", context)


@login_required
@require_http_methods(["POST"])
def document_delete(request, id_document):
    """Delete a document/image (creator or admin only)."""
    document = get_object_or_404(Document, id_document=id_document)
    old_data = {
        "type_document": document.type_document,
        "file_name": document.file_name,
        "file_size_mb": document.file_size_mb,
        "id_patrimoine": document.id_patrimoine.id_patrimoine if document.id_patrimoine else None,
        "id_inspection": document.id_inspection.id_inspection if document.id_inspection else None,
        "id_intervention": document.id_intervention.id_intervention if document.id_intervention else None,
    }
    
    # Only creator, admin, or superadmin can delete
    if not (request.user.is_superuser or 
            request.user.groups.filter(name="ADMIN").exists() or 
            document.uploaded_by == request.user):
        return redirect("patrimoine-detail", id_patrimoine=document.id_patrimoine.id_patrimoine)
    
    patrimoine_id = document.id_patrimoine.id_patrimoine if document.id_patrimoine else None
    
    # Delete physical file
    if document.file_path and default_storage.exists(document.file_path):
        default_storage.delete(document.file_path)
    
    # Delete database record
    document.delete()
    _log_audit(request.user, "DELETE", "DOCUMENT", id_document, old_data=old_data)
    
    if patrimoine_id:
        return redirect("patrimoine-detail", id_patrimoine=patrimoine_id)
    return redirect("document-list")


# ====================== USERS MANAGEMENT (Superadmin) ======================
@login_required
def user_management(request):
    """User management page (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    error = ""
    success = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "").strip().upper()

        if not email or not username or not password:
            error = "Tous les champs sont obligatoires."
        elif role not in {"ADMIN", "INSPECTEUR", "PUBLIC"}:
            error = "Rôle invalide."
        elif User.objects.filter(email=email).exists():
            error = "Cet email est déjà utilisé."
        elif User.objects.filter(username=username).exists():
            error = "Ce nom d'utilisateur est déjà utilisé."
        else:
            new_user = User.objects.create_user(username=username, email=email, password=password)
            new_user.is_active = True
            new_user.is_staff = role == "ADMIN"
            new_user.save()

            if role == "ADMIN":
                new_user.groups.add(Group.objects.get(name="ADMIN"))
            elif role == "INSPECTEUR":
                new_user.groups.add(Group.objects.get(name="INSPECTEUR"))

            # Audit log for user creation
            AuditLog.objects.create(
                actor=request.user,
                action="CREATE",
                entity_type="USER",
                entity_id=new_user.id,
                old_data=None,
                new_data={
                    "username": username,
                    "email": email,
                    "role": role,
                },
                created_at=timezone.now(),
            )
            try:
                _send_welcome_user_email(request, new_user, password, role)
                logger.info("Welcome email accepted by SMTP for user_id=%s email=%s", new_user.id, new_user.email)
                success = "Utilisateur créé avec succès. Email de bienvenue envoyé."
            except Exception as exc:
                logger.exception("Welcome email failed for user_id=%s email=%s error=%s", new_user.id, new_user.email, exc)
                success = "Utilisateur créé avec succès. Email non envoyé (vérifiez la configuration SMTP)."

    users = User.objects.all().prefetch_related("groups")
    for user in users:
        group_names = list(user.groups.values_list("name", flat=True))
        user.group_names = group_names
        user.is_admin = "ADMIN" in group_names
        user.is_inspecteur = "INSPECTEUR" in group_names
    admin_group = Group.objects.get(name="ADMIN")
    inspecteur_group = Group.objects.get(name="INSPECTEUR")
    context = {
        "users": users,
        "admin_group": admin_group,
        "inspecteur_group": inspecteur_group,
        "error": error,
        "success": success,
    }
    return render(request, "core/user_management.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_user(request, user_id):
    """Edit user profile/role (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    target_user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        username = request.POST.get("username", "").strip()
        role = request.POST.get("role", "").strip().upper()
        new_password = request.POST.get("password", "").strip()

        if not email or not username:
            messages.error(request, "Email et nom d'utilisateur sont obligatoires.")
            return redirect("edit-user", user_id=target_user.id)

        if role not in {"ADMIN", "INSPECTEUR", "PUBLIC"}:
            messages.error(request, "Rôle invalide.")
            return redirect("edit-user", user_id=target_user.id)

        if User.objects.exclude(id=target_user.id).filter(email=email).exists():
            messages.error(request, "Cet email est déjà utilisé.")
            return redirect("edit-user", user_id=target_user.id)

        if User.objects.exclude(id=target_user.id).filter(username=username).exists():
            messages.error(request, "Ce nom d'utilisateur est déjà utilisé.")
            return redirect("edit-user", user_id=target_user.id)

        old_email = target_user.email
        old_username = target_user.username

        target_user.email = email
        target_user.username = username
        target_user.is_staff = role == "ADMIN"

        if new_password:
            target_user.set_password(new_password)

        target_user.save()

        target_user.groups.clear()
        if role == "ADMIN":
            target_user.groups.add(Group.objects.get(name="ADMIN"))
        elif role == "INSPECTEUR":
            target_user.groups.add(Group.objects.get(name="INSPECTEUR"))

        try:
            _send_user_updated_email(
                request=request,
                user=target_user,
                old_email=old_email,
                old_username=old_username,
                role=role,
                raw_password=new_password or None,
            )
            logger.info("Update notification email accepted by SMTP for user_id=%s email=%s", target_user.id, target_user.email)
            messages.success(request, "Utilisateur modifié. Email de notification envoyé.")
        except Exception as exc:
            logger.exception("Update notification email failed for user_id=%s email=%s error=%s", target_user.id, target_user.email, exc)
            messages.warning(request, "Utilisateur modifié. Email de notification non envoyé.")

        return redirect("user-management")

    current_role = "PUBLIC"
    if target_user.groups.filter(name="ADMIN").exists():
        current_role = "ADMIN"
    elif target_user.groups.filter(name="INSPECTEUR").exists():
        current_role = "INSPECTEUR"

    context = {
        "target_user": target_user,
        "current_role": current_role,
    }
    return render(request, "core/user_edit.html", context)


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


@login_required
@require_http_methods(["POST"])
def update_user_email(request, user_id):
    """Update user email (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    user = get_object_or_404(User, id=user_id)
    new_email = request.POST.get("email", "").strip().lower()

    if not new_email:
        messages.error(request, "Email invalide.")
        return redirect("user-management")

    if User.objects.exclude(id=user.id).filter(email=new_email).exists():
        messages.error(request, "Cet email est déjà utilisé par un autre utilisateur.")
        return redirect("user-management")

    old_email = user.email
    user.email = new_email
    user.save(update_fields=["email"])

    messages.success(request, f"Email mis à jour pour {user.username} : {old_email} → {new_email}")
    return redirect("user-management")


@login_required
@require_http_methods(["POST"])
def delete_user(request, user_id):
    """Delete user (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    user = get_object_or_404(User, id=user_id)

    if user.id == request.user.id:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect("user-management")

    if user.is_superuser:
        messages.error(request, "Suppression d'un superadmin non autorisée depuis cet écran.")
        return redirect("user-management")

    username = user.username
    # Audit log for user deletion
    AuditLog.objects.create(
        actor=request.user,
        action="DELETE",
        entity_type="USER",
        entity_id=user.id,
        old_data={
            "username": user.username,
            "email": user.email,
            "groups": list(user.groups.values_list("name", flat=True)),
        },
        new_data=None,
        created_at=timezone.now(),
    )
    user.delete()
    messages.success(request, f"Utilisateur supprimé: {username}")
    return redirect("user-management")


# ====================== AUDIT LOG ======================
@login_required
def audit_log(request):
    """View audit log (superadmin only)."""
    if not request.user.is_superuser:
        return redirect("dashboard")

    logs = AuditLog.objects.select_related("actor").all().order_by("-created_at")

    action_filter = request.GET.get("action", "").strip()
    entity_filter = request.GET.get("entity", "").strip()
    actor_filter = request.GET.get("actor", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if action_filter:
        logs = logs.filter(action=action_filter)
    if entity_filter:
        logs = logs.filter(entity_type=entity_filter)
    if actor_filter:
        logs = logs.filter(actor_id=actor_filter)
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    action_choices = (
        AuditLog.objects.values_list("action", flat=True)
        .distinct()
        .order_by("action")
    )
    entity_choices = (
        AuditLog.objects.values_list("entity_type", flat=True)
        .distinct()
        .order_by("entity_type")
    )
    actor_choices = User.objects.filter(id__in=AuditLog.objects.values_list("actor_id", flat=True).distinct()).order_by("email")

    context = {
        "logs": logs[:300],
        "action_choices": action_choices,
        "entity_choices": entity_choices,
        "actor_choices": actor_choices,
        "filters": {
            "action": action_filter,
            "entity": entity_filter,
            "actor": actor_filter,
            "date_from": date_from,
            "date_to": date_to,
        },
    }
    return render(request, "core/audit_log.html", context)

