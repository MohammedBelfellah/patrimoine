-- ============================================================
-- Fix Foreign Key References: utilisateur → auth_user
-- Migrates all user foreign keys to Django's auth_user table
-- ============================================================

BEGIN;

-- Drop all foreign key constraints referencing utilisateur
ALTER TABLE patrimoine DROP CONSTRAINT IF EXISTS patrimoine_created_by_fkey;
ALTER TABLE inspection DROP CONSTRAINT IF EXISTS inspection_id_inspecteur_fkey;
ALTER TABLE inspection_modification_request DROP CONSTRAINT IF EXISTS inspection_modification_request_requested_by_fkey;
ALTER TABLE inspection_modification_request DROP CONSTRAINT IF EXISTS inspection_modification_request_reviewed_by_fkey;
ALTER TABLE intervention DROP CONSTRAINT IF EXISTS intervention_created_by_fkey;
ALTER TABLE document DROP CONSTRAINT IF EXISTS document_uploaded_by_fkey;
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_actor_id_fkey;

-- Drop utilisateur table (no longer needed - using Django's auth_user)
DROP TABLE IF EXISTS utilisateur CASCADE;

-- Drop the user_role enum (no longer needed)
DROP TYPE IF EXISTS user_role CASCADE;

-- Re-create foreign key constraints pointing to auth_user(id)
ALTER TABLE patrimoine 
  ADD CONSTRAINT patrimoine_created_by_fkey 
  FOREIGN KEY (created_by) REFERENCES auth_user(id) ON DELETE RESTRICT;

ALTER TABLE inspection 
  ADD CONSTRAINT inspection_id_inspecteur_fkey 
  FOREIGN KEY (id_inspecteur) REFERENCES auth_user(id) ON DELETE RESTRICT;

ALTER TABLE inspection_modification_request 
  ADD CONSTRAINT inspection_modification_request_requested_by_fkey 
  FOREIGN KEY (requested_by) REFERENCES auth_user(id) ON DELETE RESTRICT;

ALTER TABLE inspection_modification_request 
  ADD CONSTRAINT inspection_modification_request_reviewed_by_fkey 
  FOREIGN KEY (reviewed_by) REFERENCES auth_user(id) ON DELETE SET NULL;

ALTER TABLE intervention 
  ADD CONSTRAINT intervention_created_by_fkey 
  FOREIGN KEY (created_by) REFERENCES auth_user(id) ON DELETE RESTRICT;

ALTER TABLE document 
  ADD CONSTRAINT document_uploaded_by_fkey 
  FOREIGN KEY (uploaded_by) REFERENCES auth_user(id) ON DELETE RESTRICT;

ALTER TABLE audit_log 
  ADD CONSTRAINT audit_log_actor_id_fkey 
  FOREIGN KEY (actor_id) REFERENCES auth_user(id) ON DELETE RESTRICT;

-- Re-create summary view after dropping legacy utilisateur dependency
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
  COALESCE(NULLIF(TRIM(CONCAT(u.first_name, ' ', u.last_name)), ''), u.username) AS created_by_name,
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
  JOIN auth_user u ON u.id = p.created_by
  LEFT JOIN inspection i ON i.id_patrimoine = p.id_patrimoine
  LEFT JOIN intervention iv ON iv.id_patrimoine = p.id_patrimoine
GROUP BY p.id_patrimoine,
  r.nom_region,
  pr.nom_province,
  pr.type_province,
  c.nom_commune,
  c.type_commune,
  u.first_name,
  u.last_name,
  u.username;

COMMENT ON VIEW v_patrimoine_summary IS 'Vue synthétique par patrimoine avec compteurs et hiérarchie géographique complète';

COMMIT;

-- Summary
SELECT 'Foreign keys migrated successfully to auth_user table' as status;
