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

COMMIT;

-- Summary
SELECT 'Foreign keys migrated successfully to auth_user table' as status;
