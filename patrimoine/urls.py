from django.urls import path

from . import views

urlpatterns = [
    path("patrimoines/", views.patrimoine_list, name="patrimoine-list"),
    path("patrimoines/export/", views.patrimoine_export, name="patrimoine-export"),
    path("patrimoines/<int:id_patrimoine>/", views.patrimoine_detail, name="patrimoine-detail"),
    path("patrimoines/create/", views.patrimoine_create, name="patrimoine-create"),
    path("patrimoines/<int:id_patrimoine>/edit/", views.patrimoine_edit, name="patrimoine-edit"),
    path("patrimoines/<int:id_patrimoine>/delete/", views.patrimoine_delete, name="patrimoine-delete"),
    path("patrimoines/map/", views.patrimoine_map, name="patrimoine-map"),
    path("api/regions/", views.api_regions, name="api-regions"),
    path("api/provinces/<int:id_region>/", views.api_provinces_by_region, name="api-provinces"),
    path("api/communes/<int:id_province>/", views.api_communes_by_province, name="api-communes"),
    path("api/patrimoines-by-commune/<int:id_commune>/", views.api_patrimoines_by_commune, name="api-patrimoines-by-commune"),
    path("inspections/", views.inspection_list, name="inspection-list"),
    path("inspections/export/", views.inspection_export, name="inspection-export"),
    path("inspections/<int:id_inspection>/", views.inspection_detail, name="inspection-detail"),
    path("inspections/create/", views.inspection_create, name="inspection-create"),
    path("inspections/<int:id_inspection>/request-edit/", views.inspection_request_edit, name="inspection-request-edit"),
    path("inspection-requests/<int:id_request>/approve/", views.inspection_request_approve, name="inspection-request-approve"),
    path("inspection-requests/<int:id_request>/reject/", views.inspection_request_reject, name="inspection-request-reject"),
    path("interventions/", views.intervention_list, name="intervention-list"),
    path("interventions/export/", views.intervention_export, name="intervention-export"),
    path("interventions/create/", views.intervention_create, name="intervention-create"),
    path("interventions/<int:id_intervention>/", views.intervention_detail, name="intervention-detail"),
    path("interventions/<int:id_intervention>/edit/", views.intervention_edit, name="intervention-edit"),
    path("interventions/<int:id_intervention>/delete/", views.intervention_delete, name="intervention-delete"),
    path("documents/", views.document_list, name="document-list"),
    path("documents/<int:id_document>/delete/", views.document_delete, name="document-delete"),
]
