-- 1. DROP the table completely to fix all schema mismatches
-- (This is safe as it only contains 1 row of configuration)
DROP TABLE IF EXISTS settings;

-- 2. RE-CREATE the table with ALL required columns
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    university_name VARCHAR(255) DEFAULT 'Global Science University',
    registration_open BOOLEAN DEFAULT TRUE,
    maintenance_mode BOOLEAN DEFAULT FALSE,
    election_end TIMESTAMP WITHOUT TIME ZONE
);

-- 3. INSERT the default configuration
INSERT INTO settings (id, university_name, registration_open, maintenance_mode)
VALUES (1, 'Global Science University', TRUE, FALSE);

-- 4. Enable RLS (Optional, standard practice)
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public Read Settings" ON settings FOR SELECT USING (true);
CREATE POLICY "Admin Update Settings" ON settings FOR UPDATE USING (true);
