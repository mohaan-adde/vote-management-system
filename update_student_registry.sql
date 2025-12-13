-- Update student_registry table to add username and faculty columns
ALTER TABLE student_registry 
ADD COLUMN IF NOT EXISTS username TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS faculty TEXT;

-- Update the unique constraint comment
COMMENT ON COLUMN student_registry.username IS 'Unique username for each student';
COMMENT ON COLUMN student_registry.faculty IS 'Student faculty/department';
