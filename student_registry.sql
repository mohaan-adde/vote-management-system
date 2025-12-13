-- Updated simplified student_registry table schema
-- Only stores ID, Name, Phone from Excel
-- Students provide other details during registration

CREATE TABLE IF NOT EXISTS student_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    university_id TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    is_registered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Enable RLS
ALTER TABLE student_registry ENABLE ROW LEVEL SECURITY;

-- Allow public read access for registration validation
CREATE POLICY "Enable read access for all users" ON student_registry FOR SELECT USING (true);

COMMENT ON TABLE student_registry IS 'Whitelist of allowed students for registration based on ID and Phone only';
