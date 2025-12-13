-- Add phone column to profiles table for easier admin access
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS phone TEXT;

COMMENT ON COLUMN profiles.phone IS 'Student phone number for verification';
