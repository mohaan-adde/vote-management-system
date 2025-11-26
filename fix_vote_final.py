import re

# Read the file
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the old pattern (the RPC call)
old_pattern = r'supabase\.rpc\("increment_vote", \{"cid": candidate_id\}\)\.execute\(\)'

# Define the new code
new_code = '''# Get current vote count and increment it
        candidate = supabase.table("candidates").select("votes").eq("id", candidate_id).single().execute()
        current_votes = candidate.data.get("votes", 0) or 0
        new_vote_count = current_votes + 1
        
        # Update the candidate's vote count
        supabase.table("candidates").update({"votes": new_vote_count}).eq("id", candidate_id).execute()'''

# Replace
content = re.sub(old_pattern, new_code, content)

# Write back
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed successfully!")
