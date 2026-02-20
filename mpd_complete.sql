-- ============================================================
--  Patrimoine Culturel — Complete Physical Data Model (V2)
--  PostgreSQL 15+ with PostGIS 3.x
--  🇲🇦 1️⃣ Région → 2️⃣ Province/Préfecture → 3️⃣ Commune
-- ============================================================
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
-- uuid-ossp: Not used in Phase 1, uncomment if UUID PKs needed
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE user_role AS ENUM ('ADMIN', 'EDITEUR', 'INSPECTEUR');
CREATE TYPE patrimoine_type AS ENUM ('MONDIAL', 'NATUREL', 'HISTORIQUE', 'AUTRE');
CREATE TYPE patrimoine_statut AS ENUM ('CLASSE', 'INSCRIT', 'EN_ETUDE', 'AUTRE');
CREATE TYPE inspection_etat AS ENUM ('BON', 'MOYEN', 'DEGRADE');
CREATE TYPE intervention_type AS ENUM ('RESTAURATION', 'REHABILITATION', 'AUTRE');
CREATE TYPE intervention_statut AS ENUM (
    'PLANIFIEE',
    'EN_COURS',
    'SUSPENDUE',
    'TERMINEE',
    'ANNULEE'
);
CREATE TYPE document_type AS ENUM ('PDF', 'IMAGE', 'OFFICIEL', 'AUTRE');
CREATE TYPE audit_action AS ENUM (
    'CREATE',
    'UPDATE',
    'DELETE',
    'VALIDATE',
    'ARCHIVE',
    'REQUEST_EDIT',
    'REQUEST_REVIEW',
    'REQUEST_APPROVE',
    'REQUEST_REJECT'
);
CREATE TYPE audit_entity AS ENUM (
    'PATRIMOINE',
    'INSPECTION',
    'INSPECTION_REQUEST',
    'INTERVENTION',
    'DOCUMENT',
    'USER'
);
-- ============================================================
-- ENUM: inspection_request_status
-- ============================================================
CREATE TYPE inspection_request_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
-- ============================================================
-- TABLE: region (🇲🇦 Level 1)
-- ============================================================
CREATE TABLE region (
    id_region SERIAL PRIMARY KEY,
    nom_region VARCHAR(150) NOT NULL UNIQUE,
    code_region VARCHAR(10) UNIQUE
);
COMMENT ON TABLE region IS '🇲🇦 Level 1: Région du Maroc';
-- ============================================================
-- TABLE: province (2️⃣ Level 2 - Province / Préfecture)
-- ============================================================
CREATE TABLE province (
    id_province SERIAL PRIMARY KEY,
    nom_province VARCHAR(150) NOT NULL,
    code_province VARCHAR(10),
    type_province VARCHAR(50) NOT NULL,
    -- 'Préfecture' ou 'Province'
    id_region INTEGER NOT NULL REFERENCES region(id_region) ON DELETE RESTRICT,
    UNIQUE (nom_province, id_region)
);
COMMENT ON TABLE province IS '2️⃣ Level 2: Province ou Préfecture rattachée à une région';
COMMENT ON COLUMN province.type_province IS 'Préfecture ou Province';
ALTER TABLE province
ADD CONSTRAINT chk_type_province CHECK (type_province IN ('Province', 'Préfecture'));
CREATE INDEX idx_province_region ON province(id_region);
-- ============================================================
-- TABLE: commune (3️⃣ Level 3 - Commune Urbaine ou Rurale)
-- ============================================================
CREATE TABLE commune (
    id_commune SERIAL PRIMARY KEY,
    nom_commune VARCHAR(150) NOT NULL,
    code_commune VARCHAR(10),
    type_commune VARCHAR(50) NOT NULL,
    -- 'Urbaine' ou 'Rurale'
    id_province INTEGER NOT NULL REFERENCES province(id_province) ON DELETE RESTRICT,
    UNIQUE (nom_commune, id_province)
);
COMMENT ON TABLE commune IS '3️⃣ Level 3: Commune (Urbaine ou Rurale) rattachée à une province';
COMMENT ON COLUMN commune.type_commune IS 'Urbaine ou Rurale';
ALTER TABLE commune
ADD CONSTRAINT chk_type_commune CHECK (type_commune IN ('Urbaine', 'Rurale'));
CREATE INDEX idx_commune_province ON commune(id_province);
-- ============================================================
-- TABLE: utilisateur
-- ============================================================
CREATE TABLE utilisateur (
    id_user SERIAL PRIMARY KEY,
    nom_complet VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    mot_de_passe VARCHAR(255) NOT NULL,
    -- bcrypt hash
    role user_role NOT NULL DEFAULT 'EDITEUR',
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE utilisateur IS 'Utilisateurs authentifiés : ADMIN, EDITEUR, INSPECTEUR';
COMMENT ON COLUMN utilisateur.mot_de_passe IS 'Stocké en bcrypt hash — jamais en clair';
CREATE INDEX idx_utilisateur_email ON utilisateur(email);
CREATE INDEX idx_utilisateur_role ON utilisateur(role);
-- ============================================================
-- TABLE: patrimoine
-- ============================================================
CREATE TABLE patrimoine (
    id_patrimoine SERIAL PRIMARY KEY,
    nom_fr VARCHAR(300) NOT NULL,
    nom_ar VARCHAR(300),
    description TEXT,
    type_patrimoine patrimoine_type NOT NULL,
    statut patrimoine_statut NOT NULL DEFAULT 'EN_ETUDE',
    reference_administrative VARCHAR(100),
    -- PostGIS geometry
    polygon_geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    centroid_geom GEOMETRY(POINT, 4326) GENERATED ALWAYS AS (ST_PointOnSurface(polygon_geom)) STORED,
    -- FK (now through commune which links to province → region)
    id_commune INTEGER NOT NULL REFERENCES commune(id_commune) ON DELETE RESTRICT,
    CONSTRAINT chk_valid_geometry CHECK (ST_IsValid(polygon_geom)),
    created_by INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE patrimoine IS 'Entité centrale : sites du patrimoine culturel';
COMMENT ON COLUMN patrimoine.polygon_geom IS 'Contour géographique (MultiPolygon WGS84)';
COMMENT ON COLUMN patrimoine.centroid_geom IS 'Point on surface auto-généré (garanti d être DANS le polygone) via ST_PointOnSurface';
CREATE INDEX idx_patrimoine_commune ON patrimoine(id_commune);
CREATE INDEX idx_patrimoine_statut ON patrimoine(statut);
CREATE INDEX idx_patrimoine_polygon ON patrimoine USING GIST(polygon_geom);
CREATE INDEX idx_patrimoine_centroid ON patrimoine USING GIST(centroid_geom);
-- Auto-update updated_at
CREATE OR REPLACE FUNCTION fn_set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = NOW();
RETURN NEW;
END;
$$;
CREATE TRIGGER trg_patrimoine_updated_at BEFORE
UPDATE ON patrimoine FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
-- ============================================================
-- TABLE: inspection
-- ============================================================
CREATE TABLE inspection (
    id_inspection SERIAL PRIMARY KEY,
    id_patrimoine INTEGER NOT NULL REFERENCES patrimoine(id_patrimoine) ON DELETE CASCADE,
    id_inspecteur INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    date_inspection DATE NOT NULL,
    etat inspection_etat NOT NULL,
    observations TEXT,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE inspection IS 'Rapports d inspection des sites patrimoniaux - enregistrés directement (sans workflow)';
COMMENT ON COLUMN inspection.archived_at IS 'Timestamp d archivage optionnel';
-- Workflow des modifications:
-- 1️⃣ Inspecteur crée une inspection (directement = OFFICIEL)
-- 2️⃣ Si admin veut des changements: crée une demande (inspection_modification_request)
-- 3️⃣ Inspecteur peut proposer les changements via la demande (proposed_data JSONB)
-- 4️⃣ Admin revoit et approuve/rejette la demande
-- 5️⃣ Si approuvée: l'app applique les changements à l'inspection
CREATE INDEX idx_inspection_patrimoine ON inspection(id_patrimoine);
CREATE INDEX idx_inspection_inspecteur ON inspection(id_inspecteur);
CREATE INDEX idx_inspection_archived ON inspection(archived_at)
WHERE archived_at IS NOT NULL;
CREATE TRIGGER trg_inspection_updated_at BEFORE
UPDATE ON inspection FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
-- ============================================================
-- TABLE: inspection_modification_request
-- ============================================================
CREATE TABLE inspection_modification_request (
    id_request SERIAL PRIMARY KEY,
    id_inspection INTEGER NOT NULL REFERENCES inspection(id_inspection) ON DELETE CASCADE,
    requested_by INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status inspection_request_status NOT NULL DEFAULT 'PENDING',
    reviewed_by INTEGER REFERENCES utilisateur(id_user) ON DELETE
    SET NULL,
        reviewed_at TIMESTAMPTZ,
        admin_note TEXT,
        proposed_data JSONB NOT NULL,
        CONSTRAINT chk_review_coherence CHECK (
            (
                status = 'PENDING'
                AND reviewed_by IS NULL
                AND reviewed_at IS NULL
            )
            OR (
                status IN ('APPROVED', 'REJECTED')
                AND reviewed_by IS NOT NULL
                AND reviewed_at IS NOT NULL
            )
        ),
        CONSTRAINT chk_proposed_data_object CHECK (jsonb_typeof(proposed_data) = 'object')
);
COMMENT ON TABLE inspection_modification_request IS 'Demandes de modification d inspections - nécessite approbation admin';
COMMENT ON COLUMN inspection_modification_request.proposed_data IS 'Changements proposés en JSONB';
CREATE INDEX idx_imr_inspection ON inspection_modification_request(id_inspection);
CREATE INDEX idx_imr_status ON inspection_modification_request(status);
CREATE INDEX idx_imr_requested_by ON inspection_modification_request(requested_by);
CREATE INDEX idx_imr_reviewed_by ON inspection_modification_request(reviewed_by);
CREATE INDEX idx_imr_requested_at ON inspection_modification_request(requested_at DESC);
CREATE UNIQUE INDEX uq_imr_one_pending_per_inspection ON inspection_modification_request(id_inspection)
WHERE status = 'PENDING';
-- ============================================================
-- ADD FK from inspection to inspection_modification_request
-- (deferred because inspection_modification_request is created after inspection)
-- ============================================================
ALTER TABLE inspection
ADD COLUMN applied_request_id INTEGER;
ALTER TABLE inspection
ADD CONSTRAINT fk_inspection_applied_request FOREIGN KEY (applied_request_id) REFERENCES inspection_modification_request(id_request) ON DELETE
SET NULL;
COMMENT ON COLUMN inspection.applied_request_id IS 'Référence à la demande de modification appliquée (pour traçabilité)';
CREATE INDEX idx_inspection_applied_request ON inspection(applied_request_id)
WHERE applied_request_id IS NOT NULL;
-- ============================================================
-- TABLE: intervention
-- ============================================================
CREATE TABLE intervention (
    id_intervention SERIAL PRIMARY KEY,
    id_patrimoine INTEGER NOT NULL REFERENCES patrimoine(id_patrimoine) ON DELETE CASCADE,
    nom_projet VARCHAR(300) NOT NULL,
    type_intervention intervention_type NOT NULL,
    date_debut DATE NOT NULL,
    date_fin DATE,
    prestataire VARCHAR(300),
    description TEXT,
    statut intervention_statut NOT NULL DEFAULT 'PLANIFIEE',
    date_validation TIMESTAMPTZ,
    created_by INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_dates_intervention CHECK (
        date_fin IS NULL
        OR date_fin >= date_debut
    )
);
COMMENT ON TABLE intervention IS 'Projets de restauration / réhabilitation sur les patrimoines';
CREATE INDEX idx_intervention_patrimoine ON intervention(id_patrimoine);
CREATE INDEX idx_intervention_statut ON intervention(statut);
CREATE TRIGGER trg_intervention_updated_at BEFORE
UPDATE ON intervention FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
-- ============================================================
-- TABLE: document
-- ============================================================
CREATE TABLE document (
    id_document SERIAL PRIMARY KEY,
    type_document document_type NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_mb NUMERIC(5, 2) NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    -- Context FK (exactly one must be set)
    id_patrimoine INTEGER REFERENCES patrimoine(id_patrimoine) ON DELETE CASCADE,
    id_inspection INTEGER REFERENCES inspection(id_inspection) ON DELETE CASCADE,
    id_intervention INTEGER REFERENCES intervention(id_intervention) ON DELETE CASCADE,
    id_inspection_request INTEGER REFERENCES inspection_modification_request(id_request) ON DELETE CASCADE,
    CONSTRAINT chk_file_size CHECK (
        file_size_mb > 0
        AND file_size_mb <= 5
    ),
    CONSTRAINT chk_single_context CHECK (
        num_nonnulls(
            id_patrimoine,
            id_inspection,
            id_intervention,
            id_inspection_request
        ) = 1
    )
);
COMMENT ON TABLE document IS 'Pièces jointes liées à un patrimoine, inspection, intervention ou demande de modification';
COMMENT ON COLUMN document.file_size_mb IS 'Taille en MB — max 5MB (contrainte CHECK)';
COMMENT ON CONSTRAINT chk_single_context ON document IS 'Exactement un parmi id_patrimoine / id_inspection / id_intervention / id_inspection_request doit être renseigné';
CREATE INDEX idx_document_patrimoine ON document(id_patrimoine)
WHERE id_patrimoine IS NOT NULL;
CREATE INDEX idx_document_inspection ON document(id_inspection)
WHERE id_inspection IS NOT NULL;
CREATE INDEX idx_document_intervention ON document(id_intervention)
WHERE id_intervention IS NOT NULL;
CREATE INDEX idx_document_inspection_request ON document(id_inspection_request)
WHERE id_inspection_request IS NOT NULL;
CREATE INDEX idx_document_uploaded_by ON document(uploaded_by);
-- ============================================================
-- TABLE: audit_log
-- ============================================================
CREATE TABLE audit_log (
    id_log BIGSERIAL PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES utilisateur(id_user) ON DELETE RESTRICT,
    action audit_action NOT NULL,
    entity_type audit_entity NOT NULL,
    entity_id INTEGER NOT NULL,
    old_data JSONB,
    new_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE audit_log IS 'Journal d audit complet — toutes les actions utilisateurs';
COMMENT ON COLUMN audit_log.old_data IS 'Snapshot JSONB de l entité avant modification';
COMMENT ON COLUMN audit_log.new_data IS 'Snapshot JSONB de l entité après modification';
CREATE INDEX idx_audit_actor ON audit_log(actor_id);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action);
-- ============================================================
-- VIEW: v_patrimoine_summary
-- ============================================================
CREATE OR REPLACE VIEW v_patrimoine_summary AS
SELECT p.id_patrimoine,
    p.nom_fr,
    p.nom_ar,
    p.type_patrimoine,
    p.statut,
    r.nom_region,
    pr.nom_province,
    pr.type_province,
    c.nom_commune,
    c.type_commune,
    u.nom_complet AS created_by_name,
    COUNT(DISTINCT i.id_inspection) AS nb_inspections,
    COUNT(DISTINCT iv.id_intervention) AS nb_interventions,
    (
        SELECT COUNT(DISTINCT d2.id_document)
        FROM document d2
            LEFT JOIN inspection i2 ON i2.id_inspection = d2.id_inspection
            LEFT JOIN intervention iv2 ON iv2.id_intervention = d2.id_intervention
        WHERE d2.id_patrimoine = p.id_patrimoine
            OR i2.id_patrimoine = p.id_patrimoine
            OR iv2.id_patrimoine = p.id_patrimoine
    ) AS nb_documents,
    p.created_at,
    p.updated_at
FROM patrimoine p
    JOIN commune c ON c.id_commune = p.id_commune
    JOIN province pr ON pr.id_province = c.id_province
    JOIN region r ON r.id_region = pr.id_region
    JOIN utilisateur u ON u.id_user = p.created_by
    LEFT JOIN inspection i ON i.id_patrimoine = p.id_patrimoine
    LEFT JOIN intervention iv ON iv.id_patrimoine = p.id_patrimoine
GROUP BY p.id_patrimoine,
    r.nom_region,
    pr.nom_province,
    pr.type_province,
    c.nom_commune,
    c.type_commune,
    u.nom_complet;
COMMENT ON VIEW v_patrimoine_summary IS 'Vue synthétique par patrimoine avec compteurs et hiérarchie géographique complète';
-- ============================================================
-- VIEW: v_commune_full_path
-- ============================================================
CREATE OR REPLACE VIEW v_commune_full_path AS
SELECT c.id_commune,
    c.nom_commune,
    c.type_commune,
    pr.id_province,
    pr.nom_province,
    pr.type_province,
    r.id_region,
    r.nom_region,
    CONCAT(
        r.nom_region,
        ' > ',
        pr.nom_province,
        ' > ',
        c.nom_commune
    ) AS full_path
FROM commune c
    JOIN province pr ON pr.id_province = c.id_province
    JOIN region r ON r.id_region = pr.id_region;
COMMENT ON VIEW v_commune_full_path IS 'Full geographic hierarchy path for each commune';
-- ============================================================
-- END OF COMPLETE MPD V2
-- ============================================================