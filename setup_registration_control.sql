-- Create Settings Table if it doesn't exist (simpler version)
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    registration_open BOOLEAN DEFAULT TRUE,
    university_name VARCHAR(255) DEFAULT 'Global Science University', -- Keeping these for future use
    maintenance_mode BOOLEAN DEFAULT FALSE
);

-- Insert default row if not exists
INSERT INTO settings (id, registration_open)
VALUES (1, TRUE)
ON CONFLICT (id) DO NOTHING;

-- If table exists but column missing (rare but possible during dev churn)
-- ALTER TABLE settings ADD COLUMN IF NOT EXISTS registration_open BOOLEAN DEFAULT TRUE;
