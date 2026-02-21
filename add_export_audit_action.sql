-- Add EXPORT action to audit_action enum
ALTER TYPE audit_action
ADD VALUE IF NOT EXISTS 'EXPORT';