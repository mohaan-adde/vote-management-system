-- ==============================================================================
-- 🛠️ PATCH: ADD WINNER MESSAGE COLUMN
-- RUN THIS IF YOU GET "Could not find the 'winner_message' column" ERROR
-- ==============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'elections' AND column_name = 'winner_message'
    ) THEN
        ALTER TABLE elections ADD COLUMN winner_message TEXT;
    END IF;
END $$;
