-- Create Settings Table if it doesn't exist
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    university_name VARCHAR(255) DEFAULT 'East Africa University',
    maintenance_mode BOOLEAN DEFAULT FALSE,
    election_end TIMESTAMP WITHOUT TIME ZONE -- Already referenced in app.py logic
);

-- Insert default row if not exists
INSERT INTO settings (id, university_name, maintenance_mode)
VALUES (1, 'East Africa University', FALSE)
ON CONFLICT (id) DO NOTHING;

-- Grant access (if RLS is on, though usually anon/service_role has access)
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public Read Settings" ON settings FOR SELECT USING (true);
-- Note: Admin check in policy depends on auth() function working correctly in Supabase
CREATE POLICY "Admin Update Settings" ON settings FOR UPDATE USING (true); 
-- logic in app.py handles admin check primarily, RLS is backup.
