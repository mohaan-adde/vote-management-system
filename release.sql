-- ==============================================================================
-- 🛠️ VOTE SYSTEM REFACTOR SCRIPT
-- RUN THIS IN SUPABASE SQL EDITOR TO APPLY CHANGES
-- ==============================================================================

-- 1. DROP EXISTING OBJECTS COMPLELTELY TO RESET STRUCTURE (OPTIONAL BUT SAFER FOR DEV)
-- WARNING: THIS DELETES ALL DATA. IF YOU WANT TO KEEP DATA, COMMENT THESE DROPS OUT.
-- BUT SINCE YOU ASKED TO FIX ERRORS, A CLEAN SLATE IS OFTEN BEST.
DROP TABLE IF EXISTS votes CASCADE;
DROP TABLE IF EXISTS candidates CASCADE;
DROP TABLE IF EXISTS elections CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;
DROP FUNCTION IF EXISTS increment_vote CASCADE;
DROP FUNCTION IF EXISTS create_election_with_candidates CASCADE;

-- 2. ENABLE EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 3. PROFILES TABLE
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(150),
    faculty TEXT,
    university_id VARCHAR(50) UNIQUE,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now()
);

-- 4. ELECTIONS TABLE
CREATE TABLE elections (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'Upcoming', -- STATUS IS DERIVED BUT KEPT FOR CACHING
    winner_message TEXT -- Custom congratulatory message for the winner
);

-- 5. CANDIDATES TABLE
CREATE TABLE candidates (
    id SERIAL PRIMARY KEY,
    election_id INT NOT NULL REFERENCES elections(id) ON DELETE CASCADE, -- LINKED TO ELECTION
    name VARCHAR(100) NOT NULL,
    motto TEXT,
    photo TEXT,
    bio TEXT,
    department TEXT,
    year_level TEXT,
    manifesto TEXT,
    votes INT DEFAULT 0
);

-- 6. VOTES TABLE
CREATE TABLE votes (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    election_id INT NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    candidate_id INT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    voted_at TIMESTAMP DEFAULT now(),
    UNIQUE(email, election_id) -- ONE VOTE PER ELECTION PER PERSON
);

-- 7. RPC: INCREMENT VOTE
CREATE OR REPLACE FUNCTION increment_vote(cid INT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE candidates
    SET votes = votes + 1
    WHERE id = cid;
END;
$$;

-- 8. RPC: CREATE ELECTION WITH CANDIDATES (ATOMIC TRANSACTION)
CREATE OR REPLACE FUNCTION create_election_with_candidates(
    title TEXT,
    description TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    candidates_json JSONB
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    new_election_id INT;
    candidate_record JSONB;
BEGIN
    -- 1. Create Election
    INSERT INTO elections (title, description, start_time, end_time, status)
    VALUES (title, description, start_time, end_time, 'Upcoming')
    RETURNING id INTO new_election_id;

    -- 2. Loop through candidates and insert them
    FOR candidate_record IN SELECT * FROM jsonb_array_elements(candidates_json)
    LOOP
        INSERT INTO candidates (election_id, name, motto, photo, bio, department, year_level, manifesto)
        VALUES (
            new_election_id,
            candidate_record->>'name',
            candidate_record->>'motto',
            candidate_record->>'photo',
            candidate_record->>'bio',
            candidate_record->>'department',
            candidate_record->>'year_level',
            candidate_record->>'manifesto'
        );
    END LOOP;
END;
$$;

-- 9. ADMIN ACCOUNT (DEFAULT)
INSERT INTO profiles (email, name, faculty, university_id, verified)
VALUES ('admin@gsu.edu', 'System Admin', 'Administration', 'ADMIN-001', TRUE)
ON CONFLICT (email) DO NOTHING;

-- 10. SAMPLE DATA (OPTIONAL)
-- You can remove this if you want an empty system
SELECT create_election_with_candidates(
    'Hogaanka Ardayda 2026',
    'Doorashada Gudoomiyaha iyo Kuxigeenka',
    (now() + interval '1 minute')::timestamp, 
    (now() + interval '2 days')::timestamp,
    '[
        {"name": "Ahmed Ali", "motto": "Horumar", "photo": "https://placehold.co/150", "bio": "N/A", "department": "IT", "year_level": "4", "manifesto": ""},
        {"name": "Maryan Yusuf", "motto": "Sinnaan", "photo": "https://placehold.co/150", "bio": "N/A", "department": "Medicine", "year_level": "3", "manifesto": ""}
    ]'::jsonb
);
