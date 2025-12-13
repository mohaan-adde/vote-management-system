-- 1. Add the column if it doesn't exist
ALTER TABLE settings 
ADD COLUMN IF NOT EXISTS registration_open BOOLEAN DEFAULT TRUE;

-- 2. Add other columns if they are missing (just in case)
ALTER TABLE settings 
ADD COLUMN IF NOT EXISTS university_name VARCHAR(255) DEFAULT 'Global Science University',
ADD COLUMN IF NOT EXISTS maintenance_mode BOOLEAN DEFAULT FALSE;

-- 3. Update the university name to the correct one
UPDATE settings 
SET university_name = 'Global Science University' 
WHERE id = 1;

-- 4. Insert the default row if it doesn't exist at all
INSERT INTO settings (id, registration_open, university_name, maintenance_mode)
VALUES (1, TRUE, 'Global Science University', FALSE)
ON CONFLICT (id) DO NOTHING;
