# Database Migration: Add email_id Support

## Problem
Events, damages, claims, and deadlines can come from BOTH:
- **Attachments** (PDFs, docs, etc.) → use `file_id` → FK to `project_attachments`
- **Emails** → use `email_id` → FK to `project_emails`

Previously, we only had `file_id`, which caused foreign key errors when trying to save events from emails.

## Solution
Add `email_id` column to all relevant tables:
- `project_events`
- `project_damages`
- `project_claims`
- `project_deadlines`

Each row must have EITHER `file_id` OR `email_id` (not both, not neither).

## How to Apply

### Option 1: Supabase Dashboard
1. Go to https://supabase.com/dashboard
2. Select your project
3. Go to **SQL Editor**
4. Copy and paste content from `add_email_id_to_tables.sql`
5. Click **Run**

### Option 2: Supabase CLI
```bash
supabase db reset  # If you want fresh start
# OR
supabase db push  # If migration files are configured
```

## Code Changes
The Python code has been updated to:
- Set `email_id` (not `file_id`) for events/damages/claims/deadlines from emails
- Set `file_id` (not `email_id`) for events/damages/claims/deadlines from attachments
- Always set the other field to `None`

## Verification
After migration, check:
```sql
-- Events from emails should have email_id set
SELECT * FROM project_events WHERE email_id IS NOT NULL;

-- Events from attachments should have file_id set
SELECT * FROM project_events WHERE file_id IS NOT NULL;

-- No rows should have both or neither
SELECT * FROM project_events WHERE 
  (file_id IS NOT NULL AND email_id IS NOT NULL) OR 
  (file_id IS NULL AND email_id IS NULL);
-- Should return 0 rows
```
