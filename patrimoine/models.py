from django.contrib.gis.db import models as gis_models
from django.db import models


class Region(models.Model):
    id_region = models.AutoField(primary_key=True, db_column="id_region")
    nom_region = models.CharField(max_length=150, unique=True, db_column="nom_region")
    code_region = models.CharField(max_length=10, null=True, blank=True, db_column="code_region")

    class Meta:
        managed = False
        db_table = "region"
        verbose_name = "Région"
        verbose_name_plural = "Régions"

    def __str__(self):
        return self.nom_region


class Province(models.Model):
    PROVINCE_TYPES = [("Province", "Province"), ("Préfecture", "Préfecture")]

    id_province = models.AutoField(primary_key=True, db_column="id_province")
    nom_province = models.CharField(max_length=150, db_column="nom_province")
    code_province = models.CharField(max_length=10, null=True, blank=True, db_column="code_province")
    type_province = models.CharField(max_length=50, choices=PROVINCE_TYPES, db_column="type_province")
    id_region = models.ForeignKey(Region, on_delete=models.PROTECT, db_column="id_region")

    class Meta:
        managed = False
        db_table = "province"
        unique_together = [["nom_province", "id_region"]]
        verbose_name = "Province/Préfecture"
        verbose_name_plural = "Provinces/Préfectures"

    def __str__(self):
        return f"{self.nom_province} ({self.type_province})"


class Commune(models.Model):
    COMMUNE_TYPES = [("Urbaine", "Urbaine"), ("Rurale", "Rurale")]

    id_commune = models.AutoField(primary_key=True, db_column="id_commune")
    nom_commune = models.CharField(max_length=150, db_column="nom_commune")
    code_commune = models.CharField(max_length=10, null=True, blank=True, db_column="code_commune")
    type_commune = models.CharField(max_length=50, choices=COMMUNE_TYPES, db_column="type_commune")
    id_province = models.ForeignKey(Province, on_delete=models.PROTECT, db_column="id_province")

    class Meta:
        managed = False
        db_table = "commune"
        unique_together = [["nom_commune", "id_province"]]
        verbose_name = "Commune"
        verbose_name_plural = "Communes"

    def __str__(self):
        return self.nom_commune

    @property
    def region(self):
        return self.id_province.id_region


class Patrimoine(models.Model):
    PATRIMOINE_TYPES = [
        ("MONDIAL", "Patrimoine Mondial"),
        ("NATUREL", "Patrimoine Naturel"),
        ("HISTORIQUE", "Monument Historique"),
        ("AUTRE", "Autres Types"),
    ]
    PATRIMOINE_STATUTS = [
        ("CLASSE", "Classé"),
        ("INSCRIT", "Inscrit"),
        ("EN_ETUDE", "En cours d'étude"),
        ("AUTRE", "Autre"),
    ]

    id_patrimoine = models.AutoField(primary_key=True, db_column="id_patrimoine")
    nom_fr = models.CharField(max_length=300, db_column="nom_fr")
    nom_ar = models.CharField(max_length=300, null=True, blank=True, db_column="nom_ar")
    description = models.TextField(null=True, blank=True, db_column="description")
    type_patrimoine = models.CharField(max_length=50, choices=PATRIMOINE_TYPES, db_column="type_patrimoine")
    statut = models.CharField(max_length=50, choices=PATRIMOINE_STATUTS, default="EN_ETUDE", db_column="statut")
    reference_administrative = models.CharField(max_length=100, null=True, blank=True, db_column="reference_administrative")
    polygon_geom = gis_models.MultiPolygonField(srid=4326, db_column="polygon_geom")
    centroid_geom = gis_models.PointField(srid=4326, null=True, blank=True, db_column="centroid_geom")
    id_commune = models.ForeignKey(Commune, on_delete=models.PROTECT, db_column="id_commune")
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="patrimoines_created",
        db_column="created_by",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField(auto_now=True, db_column="updated_at")

    class Meta:
        managed = False
        db_table = "patrimoine"
        verbose_name = "Patrimoine"
        verbose_name_plural = "Patrimoines"

    def __str__(self):
        return f"{self.nom_fr} ({self.type_patrimoine})"

    @property
    def full_location(self):
        commune = self.id_commune
        province = commune.id_province
        region = province.id_region
        return f"{region.nom_region} > {province.nom_province} > {commune.nom_commune}"


class Inspection(models.Model):
    INSPECTION_ETAT = [("BON", "Bon"), ("MOYEN", "Moyen"), ("DEGRADE", "Dégradé")]

    id_inspection = models.AutoField(primary_key=True, db_column="id_inspection")
    id_patrimoine = models.ForeignKey(Patrimoine, on_delete=models.CASCADE, db_column="id_patrimoine")
    id_inspecteur = models.ForeignKey("auth.User", on_delete=models.PROTECT, db_column="id_inspecteur", related_name="inspections")
    date_inspection = models.DateField(db_column="date_inspection")
    etat = models.CharField(max_length=50, choices=INSPECTION_ETAT, db_column="etat")
    observations = models.TextField(null=True, blank=True, db_column="observations")
    archived_at = models.DateTimeField(null=True, blank=True, db_column="archived_at")
    created_at = models.DateTimeField(auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField(auto_now=True, db_column="updated_at")

    class Meta:
        managed = False
        db_table = "inspection"
        verbose_name = "Inspection"
        verbose_name_plural = "Inspections"

    def __str__(self):
        return f"Inspection {self.id_patrimoine.nom_fr} - {self.date_inspection}"


class InspectionModificationRequest(models.Model):
    """Inspection modification requests - Inspecteur proposes changes, Admin approves/rejects."""

    REQUEST_STATUS = [("PENDING", "En attente"), ("APPROVED", "Approuvée"), ("REJECTED", "Rejetée")]

    id_request = models.AutoField(primary_key=True, db_column="id_request")
    id_inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, db_column="id_inspection", related_name="modification_requests")
    requested_by = models.ForeignKey("auth.User", on_delete=models.PROTECT, db_column="requested_by", related_name="inspection_requests_made")
    requested_at = models.DateTimeField(auto_now_add=True, db_column="requested_at")
    status = models.CharField(max_length=50, choices=REQUEST_STATUS, default="PENDING", db_column="status")
    reviewed_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, db_column="reviewed_by", related_name="inspection_requests_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True, db_column="reviewed_at")
    admin_note = models.TextField(null=True, blank=True, db_column="admin_note")
    proposed_data = models.JSONField(db_column="proposed_data")

    class Meta:
        managed = False
        db_table = "inspection_modification_request"
        verbose_name = "Demande de modification d'inspection"
        verbose_name_plural = "Demandes de modification d'inspection"

    def __str__(self):
        return f"Demande #{self.id_request} - {self.get_status_display()}"


class Intervention(models.Model):
    INTERVENTION_TYPES = [("RESTAURATION", "Restauration"), ("REHABILITATION", "Réhabilitation"), ("AUTRE", "Autre")]
    INTERVENTION_STATUTS = [
        ("PLANIFIEE", "Planifiée"),
        ("EN_COURS", "En cours"),
        ("SUSPENDUE", "Suspendue"),
        ("TERMINEE", "Terminée"),
        ("ANNULEE", "Annulée"),
    ]

    id_intervention = models.AutoField(primary_key=True, db_column="id_intervention")
    id_patrimoine = models.ForeignKey(Patrimoine, on_delete=models.CASCADE, db_column="id_patrimoine")
    nom_projet = models.CharField(max_length=300, db_column="nom_projet")
    type_intervention = models.CharField(max_length=50, choices=INTERVENTION_TYPES, db_column="type_intervention")
    date_debut = models.DateField(db_column="date_debut")
    date_fin = models.DateField(null=True, blank=True, db_column="date_fin")
    prestataire = models.CharField(max_length=300, null=True, blank=True, db_column="prestataire")
    description = models.TextField(null=True, blank=True, db_column="description")
    statut = models.CharField(max_length=50, choices=INTERVENTION_STATUTS, default="PLANIFIEE", db_column="statut")
    date_validation = models.DateTimeField(null=True, blank=True, db_column="date_validation")
    created_by = models.ForeignKey("auth.User", on_delete=models.PROTECT, db_column="created_by", related_name="interventions_created")
    created_at = models.DateTimeField(auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField(auto_now=True, db_column="updated_at")

    class Meta:
        managed = False
        db_table = "intervention"
        verbose_name = "Intervention"
        verbose_name_plural = "Interventions"

    def __str__(self):
        return f"{self.nom_projet} ({self.statut})"


class Document(models.Model):
    DOCUMENT_TYPES = [("PDF", "PDF"), ("IMAGE", "Image"), ("OFFICIEL", "Officiel"), ("AUTRE", "Autre")]

    id_document = models.AutoField(primary_key=True, db_column="id_document")
    type_document = models.CharField(max_length=50, choices=DOCUMENT_TYPES, db_column="type_document")
    file_name = models.CharField(max_length=255, db_column="file_name")
    file_path = models.TextField(db_column="file_path")
    file_size_mb = models.DecimalField(max_digits=5, decimal_places=2, db_column="file_size_mb")
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column="uploaded_at")
    uploaded_by = models.ForeignKey("auth.User", on_delete=models.PROTECT, db_column="uploaded_by")
    id_patrimoine = models.ForeignKey(Patrimoine, null=True, blank=True, on_delete=models.CASCADE, db_column="id_patrimoine")
    id_inspection = models.ForeignKey(Inspection, null=True, blank=True, on_delete=models.CASCADE, db_column="id_inspection")
    id_intervention = models.ForeignKey(Intervention, null=True, blank=True, on_delete=models.CASCADE, db_column="id_intervention")

    class Meta:
        managed = False
        db_table = "document"
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return self.file_name

