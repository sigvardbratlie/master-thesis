-- Migration: Add email_id column to support events/damages/claims/deadlines from emails
-- Date: 2026-02-10
-- Description: Events/damages/claims/deadlines can come from either attachments OR emails.
--              We add email_id and make file_id nullable to support both sources.

-- 1. Add email_id column to project_events
ALTER TABLE project_events 
ADD COLUMN IF NOT EXISTS email_id UUID;

-- Add foreign key to project_emails
ALTER TABLE project_events
ADD CONSTRAINT project_events_email_id_fkey 
FOREIGN KEY (email_id) REFERENCES project_emails(email_id) ON DELETE CASCADE;

-- Make file_id nullable (it's NULL when event comes from email)
ALTER TABLE project_events 
ALTER COLUMN file_id DROP NOT NULL;

-- Add check constraint: must have either file_id OR email_id (not both, not neither)
ALTER TABLE project_events
ADD CONSTRAINT project_events_source_check 
CHECK (
  (file_id IS NOT NULL AND email_id IS NULL) OR 
  (file_id IS NULL AND email_id IS NOT NULL)
);

-- 2. Add email_id column to project_damages
ALTER TABLE project_damages 
ADD COLUMN IF NOT EXISTS email_id UUID;

ALTER TABLE project_damages
ADD CONSTRAINT project_damages_email_id_fkey 
FOREIGN KEY (email_id) REFERENCES project_emails(email_id) ON DELETE CASCADE;

ALTER TABLE project_damages 
ALTER COLUMN file_id DROP NOT NULL;

ALTER TABLE project_damages
ADD CONSTRAINT project_damages_source_check 
CHECK (
  (file_id IS NOT NULL AND email_id IS NULL) OR 
  (file_id IS NULL AND email_id IS NOT NULL)
);

-- 3. Add email_id column to project_claims
ALTER TABLE project_claims 
ADD COLUMN IF NOT EXISTS email_id UUID;

ALTER TABLE project_claims
ADD CONSTRAINT project_claims_email_id_fkey 
FOREIGN KEY (email_id) REFERENCES project_emails(email_id) ON DELETE CASCADE;

ALTER TABLE project_claims 
ALTER COLUMN file_id DROP NOT NULL;

ALTER TABLE project_claims
ADD CONSTRAINT project_claims_source_check 
CHECK (
  (file_id IS NOT NULL AND email_id IS NULL) OR 
  (file_id IS NULL AND email_id IS NOT NULL)
);

-- 4. Add email_id column to project_deadlines
ALTER TABLE project_deadlines 
ADD COLUMN IF NOT EXISTS email_id UUID;

ALTER TABLE project_deadlines
ADD CONSTRAINT project_deadlines_email_id_fkey 
FOREIGN KEY (email_id) REFERENCES project_emails(email_id) ON DELETE CASCADE;

ALTER TABLE project_deadlines 
ALTER COLUMN file_id DROP NOT NULL;

ALTER TABLE project_deadlines
ADD CONSTRAINT project_deadlines_source_check 
CHECK (
  (file_id IS NOT NULL AND email_id IS NULL) OR 
  (file_id IS NULL AND email_id IS NOT NULL)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_project_events_email_id ON project_events(email_id);
CREATE INDEX IF NOT EXISTS idx_project_damages_email_id ON project_damages(email_id);
CREATE INDEX IF NOT EXISTS idx_project_claims_email_id ON project_claims(email_id);
CREATE INDEX IF NOT EXISTS idx_project_deadlines_email_id ON project_deadlines(email_id);
