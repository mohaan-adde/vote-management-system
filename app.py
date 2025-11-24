from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import supabase
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
# IMPORTANT: Replace the default secret key in a production environment
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
# For browser/frontend usage, ensure this is the public anon key.
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", os.getenv("SUPABASE_KEY", ""))

# Storage bucket for candidate photos (MUST be a public bucket in Supabase)
BUCKET_NAME = os.getenv("CANDIDATE_BUCKET", "candidate-photos")

# -------------------- HELPER FUNCTIONS --------------------

def get_election_end():
    """Return election end timestamp string in ISO format (or None if not set)."""
    try:
        # Fetch the single settings row (assuming ID 1 is used for global settings)
        data = (
            supabase.table("settings").select("election_end").eq("id", 1).limit(1).single().execute().data
        )
        return data.get("election_end") if data else None
    except Exception as e:
        print(f"Error fetching election end: {e}")
        return None


def election_is_active(now_dt=None):
    """Checks if the current time is before the election end time."""
    end_iso = get_election_end()
    if not end_iso:
        # If no end time is set, assume the election is always active
        return True
    try:
        # Normalize Z to +00:00 for fromisoformat and handle potential timezone issues
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        now_dt = now_dt or datetime.now(timezone.utc)
        return now_dt < end_dt
    except Exception as e:
        print(f"Error checking election status: {e}. Defaulting to active.")
        return True


def is_user_verified(email: str) -> bool:
    """Checks the 'verified' status for a user profile."""
    if email == "admin@gsu.edu":
        # Admin is always considered verified for access
        return True
    try:
        # Fetch 'verified' status from the profiles table
        row = supabase.table("profiles").select("verified").eq("email", email).single().execute().data
        return bool(row and row.get("verified"))
    except Exception as e:
        print(f"Error checking user verification for {email}: {e}")
        return False

def handle_photo_upload(file, name, existing_photo=None):
    """Uploads a file to Supabase Storage and returns the public URL."""
    if not file or not file.filename:
        return existing_photo
    
    try:
        ext = os.path.splitext(file.filename)[1].lower()
        # Create a unique filename
        fname = f"candidate_{int(time.time())}_{secure_filename(name)}{ext}"
        
        file_bytes = file.read()
        print(f"[STORAGE] Uploading photo to bucket {BUCKET_NAME} as {fname}")
        
        # Upload the file
        upload_response = supabase.storage.from_(BUCKET_NAME).upload(
            file=file_bytes, 
            path=fname, 
            file_options={"content-type": file.mimetype, "upsert": True}
        )
        
        # Get the public URL
        public_url_response = supabase.storage.from_(BUCKET_NAME).get_public_url(fname)

        photo_url = ""
        try:
            # Handle various possible response shapes from different Supabase SDK versions
            if isinstance(public_url_response, str):
                # SDK returns a string directly
                photo_url = public_url_response
            elif isinstance(public_url_response, dict):
                # Fallback for dict responses
                photo_url = public_url_response.get("publicUrl") or public_url_response.get("public_url") or public_url_response.get("publicURL") or ""
            else:
                # Some SDKs return an object with a 'data' attribute containing the URL
                data = getattr(public_url_response, "data", None)
                if isinstance(data, dict):
                    photo_url = data.get("publicUrl") or data.get("public_url") or ""
                else:
                    # Last resort: try string conversion
                    try:
                        photo_url = str(public_url_response)
                    except Exception:
                        photo_url = ""
        except Exception:
            photo_url = ""
        # Final fallback: Construct URL manually
        if not photo_url and SUPABASE_URL:
            photo_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET_NAME}/{fname}"

        if not photo_url:
             print(f"[STORAGE ERROR] Photo uploaded but public URL could not be determined.")
             return existing_photo # Use existing or return None
        
        return photo_url
        
    except Exception as e:
        print(f"[STORAGE ERROR] Failed to upload candidate photo: {repr(e)}")
        flash("Failed to upload candidate photo to Supabase. Check server logs.", "error")
        return existing_photo


# -------------------- HOME --------------------
@app.route("/")
def home():
    """Landing page showing election statistics and top candidates."""
    candidates = []
    votes = []
    profiles = []

    try:
        # Select required candidate info and sort by votes in Python
        candidates_raw = supabase.table("candidates").select("id,name,photo,votes").execute().data or []
    except Exception:
        candidates_raw = []

    try:
        votes = supabase.table("votes").select("id").execute().data or []
    except Exception:
        votes = []

    try:
        # Profiles count is used for total registered
        profiles = supabase.table("profiles").select("id").execute().data or []
    except Exception:
        profiles = []

    # Calculate statistics
    candidates_sorted = sorted(candidates_raw, key=lambda x: x.get("votes", 0) or 0, reverse=True)
    top_candidates = candidates_sorted[:3]

    total_registered = len(profiles)
    total_voted = len(votes)
    max_votes = candidates_sorted[0].get("votes", 0) if candidates_sorted else 0
    
    turnout = 0
    if total_registered > 0:
        turnout = int(round((total_voted * 100) / total_registered))

    hero_stats = {
        "total_registered": total_registered,
        "total_voted": total_voted,
        "turnout": turnout,
        "max_votes": max_votes,
    }

    return render_template(
        "home.html",
        election_end_iso=get_election_end(),
        hero_stats=hero_stats,
        top_candidates=top_candidates,
    )

# -------------------- REGISTER --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration route."""
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        name = request.form.get("name", "").strip()
        if not name:
            name = (first_name + " " + last_name).strip()

        university_id = request.form.get("university_id", "").strip()
        faculty = request.form.get("faculty", "").strip()
        email = request.form["email"]
        password = request.form["password"]

        if not all([name, university_id, email, password]):
             flash("Please fill out all required fields.", "error")
             return redirect(url_for("register"))

        # 🛑 1. Check if University ID is already used
        try:
            existing_id = supabase.table("profiles").select("id").eq("university_id", university_id).execute()
            if existing_id.data:
                flash("This University ID is already registered. Please contact admin.", "error")
                return redirect(url_for("register"))
        except Exception as e:
            print(f"Error checking University ID: {e}")
            flash("Database error during ID check.", "error")
            return redirect(url_for("register"))

        try:
            # 2. Create user via Auth
            response = supabase.auth.sign_up({"email": email, "password": password})

            # 3. Save profile data
            supabase.table("profiles").insert({
                "email": email,
                "name": name,
                "faculty": faculty,
                "university_id": university_id,
                "verified": False # User needs admin verification
            }).execute()

            flash("Registration successful. Check your email for confirmation (if email confirmation is enabled on Supabase). Your account is now pending admin verification.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Registration failed: {str(e)}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


# -------------------- LOGIN --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    """User login route."""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            
            # Supabase Python SDK often puts the user object inside the session key
            user = response.user if hasattr(response, 'user') else (response.session.user if hasattr(response, 'session') and response.session else None)
            
            if user:
                session["user"] = user.email
                session["user_id"] = user.id
                
                # Special handling for Admin login
                if user.email == "admin@gsu.edu":
                    flash("Admin logged in successfully.", "success")
                    return redirect(url_for("admin_dashboard"))
                
                # Ensure profile exists for non-admins and check verification status
                if not is_user_verified(user.email):
                    flash("Login successful. Account is pending admin verification.", "warning")
                    return redirect(url_for("pending_verification"))
                
                flash("Logged in successfully.", "success")
                return redirect(url_for("vote"))
            else:
                flash("Login failed. Could not retrieve user session.", "error")
        
        except Exception as e:
            msg = str(e)
            if "Invalid login credentials" in msg:
                flash("Incorrect email or password.", "error")
            elif "Email not confirmed" in msg:
                flash("Please verify your email before logging in.", "warning")
            else:
                print(f"Login Exception: {e}")
                flash("Login failed. Check your internet or Supabase configuration.", "error")
        
        return redirect(url_for("login"))
    return render_template("login.html")

# -------------------- FORGOT PASSWORD --------------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Route to request a password reset email."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your email address.", "warning")
            return redirect(url_for("forgot_password"))
        try:
            redirect_url = url_for("update_password", _external=True)
            supabase.auth.reset_password_for_email(email, options={"redirectTo": redirect_url}) # Use redirectTo for modern Supabase
            flash("If that email exists, a password reset link has been sent. Open it to set a new password.", "info")
        except Exception:
            flash("Could not send password reset email. Please try again later.", "error")
        return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/update-password", methods=["GET"])
def update_password():
    """Password reset landing page after clicking the email link."""
    return render_template(
        "update_password.html",
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY,
    )

# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    """User logout route."""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# -------------------- PENDING VERIFICATION --------------------
@app.route("/pending")
def pending_verification():
    """Page shown while waiting for admin verification."""
    if 'user' not in session:
        return redirect(url_for("login"))
    
    if is_user_verified(session.get('user')):
        return redirect(url_for("vote"))
        
    return render_template("pending_verification.html")


# -------------------- CONTACT --------------------
@app.route("/contact")
def contact():
    """Contact information page."""
    return render_template("contact.html")


# -------------------- TERMS --------------------
@app.route("/terms")
def terms():
    """Terms and conditions page."""
    return render_template("terms.html", no_nav=True)

# -------------------- VOTING --------------------
@app.route("/vote")
def vote():
    """Voting page, listing candidates and showing vote status."""
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    user_email = session['user']

    # Check if election is active
    if not election_is_active():
        flash("The election is currently closed. Results will be available soon.", "error")
        return redirect(url_for("results"))

    # Admin cannot vote
    if user_email == "admin@gsu.edu":
        flash("Admins are not allowed to vote.", "error")
        return redirect(url_for("admin_dashboard"))

    # Only verified users vote
    if not is_user_verified(user_email):
        flash("Your account is still awaiting verification.", "warning")
        return redirect(url_for("pending_verification"))

    # Load candidates
    try:
        candidates = supabase.table("candidates").select("*").execute().data
    except Exception as e:
        print("CANDIDATE LOAD ERROR:", e)
        flash("Unable to load candidates. Please try again.", "error")
        candidates = []

    # Check if user already voted
    try:
        vote_check = supabase.table("votes") \
            .select("id") \
            .eq("email", user_email) \
            .execute().data

        has_voted = True if vote_check else False
    except Exception as e:
        print("VOTE CHECK ERROR:", e)
        flash("Could not verify your voting status.", "error")
        has_voted = False

    # Sort by votes
    try:
        candidates = sorted(candidates, key=lambda x: x.get("votes", 0) or 0, reverse=True)
    except:
        pass

    return render_template(
        "vote.html",
        candidates=candidates,
        user=user_email,
        has_voted=has_voted,
        election_end_iso=get_election_end(),
        election_active=election_is_active()
    )


@app.route("/vote/<int:candidate_id>", methods=["POST"])
def submit_vote(candidate_id):
    """Handles voting."""
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    email = session['user']

    # Must be verified
    if not is_user_verified(email):
        flash("You must be verified to vote.", "warning")
        return redirect(url_for("pending_verification"))

    # Election must be active
    if not election_is_active():
        flash("Voting period has already ended.", "error")
        return redirect(url_for("vote"))

    # Check if already voted
    try:
        existing = supabase.table("votes").select("id").eq("email", email).execute().data
        if existing:
            flash("You have already voted.", "warning")
            return redirect(url_for("vote"))
    except Exception as e:
        print("VOTE CHECK ERROR:", e)
        flash("Unable to check your previous vote. Please try again.", "error")
        return redirect(url_for("vote"))

    # Record vote
    try:
        supabase.table("votes").insert({"email": email, "candidate_id": candidate_id}).execute()
        supabase.rpc("increment_vote", {"cid": candidate_id}).execute()

        flash("Your vote was successfully recorded!", "success")
    except Exception as e:
        print("VOTE INSERT/RPC ERROR:", e)

        # Here we fix the repeated error you complained about
        flash("Your vote could not be recorded. Please try again or contact admin.", "error")

    return redirect(url_for("vote"))


# -------------------- RESULTS --------------------
@app.route('/results')
def results():
    """Displays the current election results."""
    try:
        # Get all candidates and sort by votes
        candidates = supabase.table('candidates').select('*').execute().data
        candidates = sorted(candidates, key=lambda x: x.get('votes', 0) or 0, reverse=True)
    except Exception as e:
        print(f"RESULTS LOAD ERROR: {e}")
        candidates = []
        flash("Unable to load results.", "error")
        
    # Check if results should only be shown after election ends
    show_live_results = True # Change this to False if you only want to show results after election_is_active() is False
    
    if not show_live_results and election_is_active():
        flash("Results are not available until the voting period ends.", "info")
        # Only show names/mottos, but zero out votes for display if not active
        safe_candidates = [{**c, 'votes': 0} for c in candidates]
        return render_template('results.html', candidates=safe_candidates, results_available=False)
        
    return render_template('results.html', candidates=candidates, results_available=True)

from datetime import datetime

@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    """Admin route with Dynamic Election Status (Upcoming → Active → Closed)."""

    # -------------------------------
    # 1. Security Check
    # -------------------------------
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    # -------------------------------
    # 2. POST REQUESTS (Create/Edit/Add Candidate)
    # -------------------------------
    if request.method == "POST":
        action = request.form.get("action")

        # CREATE or EDIT election
        if action in ["create_election", "edit_election"]:
            title = request.form.get("title", "").strip()
            start_input = request.form.get("start_time", "").strip()
            end_input = request.form.get("end_time", "").strip()

            if not (title and start_input and end_input):
                flash("Please fill all fields.", "error")
                return redirect(url_for("admin_dashboard"))

            try:
                # Iska ilaaw Timezone-ka marka hore, qaado waqtiga sida uu yahay
                start_dt = datetime.fromisoformat(start_input)
                end_dt = datetime.fromisoformat(end_input)
            except ValueError:
                flash("Invalid date format.", "error")
                return redirect(url_for("admin_dashboard"))

            if end_dt <= start_dt:
                flash("End date must be after Start date.", "error")
                return redirect(url_for("admin_dashboard"))

            # Halkan status-ka "Active" ka dhig haddii waqtiga la joogo
            # Laakiin dynamic update-ka hoose ayaa saxaya mar walba
            data = {
                "title": title,
                "description": request.form.get("description", ""),
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "status": "Upcoming" 
            }

            try:
                if action == "create_election":
                    supabase.table("elections").insert(data).execute()
                    flash("Election created!", "success")
                else:
                    eid = request.form.get("election_id")
                    supabase.table("elections").update(data).eq("id", eid).execute()
                    flash("Election updated!", "success")

            except Exception as e:
                flash(f"Error: {str(e)}", "error")

            return redirect(url_for("admin_dashboard"))

        # ADD candidate
        elif action == "add_candidate":
            try:
                name = request.form["name"]
                eid = request.form["election_id"]

                photo = f"https://placehold.co/150x150/003049/ffffff?text={name[:2].upper()}"

                supabase.table("candidates").insert({
                    "election_id": eid,
                    "name": name,
                    "motto": request.form.get("motto", ""),
                    "votes": 0,
                    "photo": photo
                }).execute()

                flash("Candidate added!", "success")

            except Exception as e:
                flash(f"Error: {str(e)}", "error")

            return redirect(url_for("admin_dashboard"))

    # =====================================================
    # 3. GET REQUEST — Dynamic Election Status & Formatting
    # =====================================================

    elections_data = (
        supabase.table("elections")
        .select("*")
        .order("id", desc=True)
        .execute()
        .data or []
    )

    # ISTICMAAL LOCAL TIME (Naive) si looga fogaado khaladka Timezone-ka
    now = datetime.now() 

    for e in elections_data:
        raw_start = e.get("start_time")
        raw_end = e.get("end_time")

        if raw_start and raw_end:
            try:
                # 1. Ka saar "Z" ama "+00:00" si aad u hesho waqti saafi ah (Naive)
                # Tani waxay ka dhigeysaa waqtiga DB mid la mid ah waqtiga server-kaaga (Now)
                start_dt = datetime.fromisoformat(raw_start.replace("Z", ""))
                end_dt = datetime.fromisoformat(raw_end.replace("Z", ""))

                # Remove timezone info if it exists (make it naive)
                start_dt = start_dt.replace(tzinfo=None)
                end_dt = end_dt.replace(tzinfo=None)

                # -----------------------
                # AUTO STATUS UPDATE (FIXED)
                # -----------------------
                # Hadda isbarbardhiggu waa sax (Labada dhinacba waa Naive)
                
                new_status = "Closed" # Default

                if now < start_dt:
                    new_status = "Upcoming"
                elif start_dt <= now <= end_dt:
                    new_status = "Active"
                else:
                    new_status = "Closed"

                # Update DB only if status actually changed
                if e["status"] != new_status:
                    supabase.table("elections").update({"status": new_status}).eq("id", e["id"]).execute()
                    e["status"] = new_status # Update local variable for display

                # Readable date format
                e["start_time"] = start_dt.strftime("%d %b %Y, %I:%M %p")
                e["end_time"] = end_dt.strftime("%d %b %Y, %I:%M %p")

            except Exception as err:
                print("Date Error:", err)
                e["status"] = "Error"

    # Active & Upcoming only (for dropdown)
    active_elections = [x for x in elections_data if x["status"] in ["Active", "Upcoming"]]

    # Candidates
    candidates = supabase.table("candidates").select("*").execute().data or []
    
    # Votes
    votes = supabase.table("votes").select("*").execute().data or []
    cand_map = {c["id"]: c["name"] for c in candidates}

    voters_list = []
    for v in votes:
        vt = v.get("voted_at")
        formatted_vote_time = "-"
        if vt:
            try:
                # Format vote time safely
                vote_dt = datetime.fromisoformat(vt.replace("Z", "")).replace(tzinfo=None)
                formatted_vote_time = vote_dt.strftime("%d %b, %I:%M %p")
            except:
                formatted_vote_time = vt

        voters_list.append({
            "user_email": v.get("email"),
            "candidate_name": cand_map.get(v.get("candidate_id"), "Unknown"),
            "voted_at": formatted_vote_time
        })

    # Profiles
    profiles = supabase.table("profiles").select("*").execute().data or []
    unverified_count = sum(1 for p in profiles if not p.get("verified"))

    return render_template(
        "admin_dashboard.html",
        elections=elections_data,
        active_elections=active_elections,
        candidates=candidates,
        voters=voters_list,
        profiles=profiles,
        unverified_count=unverified_count
    )



# ======================================================================
# 2. NEW ROUTES FOR USER MANAGEMENT (Ku dar qeybtan hoose faylkaaga)
# ======================================================================

@app.route('/admin/bulk-verify', methods=['POST'])
def bulk_verify_users():
    """Route to handle bulk verification of users."""
    
    # Security Check
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    # Get list of emails from checkboxes
    selected_emails = request.form.getlist('emails')
    
    if not selected_emails:
        flash('Fadlan dooro ugu yaraan hal qof.', 'warning')
        return redirect(url_for('admin_dashboard'))

    try:
        # Supabase update: Update 'verified' to True for all emails in the list
        response = supabase.table("profiles") \
            .update({"verified": True}) \
            .in_("email", selected_emails) \
            .execute()
            
        flash(f'{len(selected_emails)} users have been verified successfully.', 'success')
        
    except Exception as e:
        flash(f'Error verifying users: {str(e)}', 'error')
        print(f"Bulk Verify Error: {e}")

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-user', methods=['POST'])
def delete_user():
    """Route to handle single user deletion."""
    
    # Security Check
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    email = request.form.get('email')
    
    if not email:
        flash('Khalad: Email lama helin.', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        # Supabase delete: Remove the user from profiles table
        supabase.table("profiles").delete().eq("email", email).execute()
        
        flash(f'User {email} deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
        print(f"Delete Error: {e}")

    return redirect(url_for('admin_dashboard'))

# -------------------- DELETE CANDIDATE --------------------
@app.route("/admin/delete/<int:candidate_id>")
def delete_candidate(candidate_id):
    """Admin route to delete a candidate."""
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))
    try:
        # Also delete associated votes (optional, depending on DB cascading rules)
        supabase.table("votes").delete().eq("candidate_id", candidate_id).execute()
        supabase.table("candidates").delete().eq("id", candidate_id).execute()
        flash("Candidate and associated votes deleted successfully!", "success")
    except Exception as e:
        flash(f"Could not delete candidate: {str(e)}", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------- EDIT CANDIDATE --------------------
@app.route("/admin/edit/<int:candidate_id>", methods=["POST"])
def edit_candidate(candidate_id):
    """Admin route to edit an existing candidate."""
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    motto = request.form["motto"].strip()
    bio = request.form.get("bio", "").strip()
    department = request.form.get("department", "").strip()
    year_level = request.form.get("year_level", "").strip()
    manifesto = request.form.get("manifesto", "").strip()
    
    # Preserve current photo URL in case no new file is uploaded
    current_photo_url = request.form.get("current_photo_url") 
    file = request.files.get("photo_file")
    
    # Handle photo upload or keep the existing one
    new_photo_url = handle_photo_upload(file, name, existing_photo=current_photo_url)
    
    if not new_photo_url:
        new_photo_url = f"https://placehold.co/150x150/003049/ffffff?text={name[0:2].upper()}"

    update_data = {
        "name": name,
        "motto": motto,
        "photo": new_photo_url,
        "bio": bio,
        "department": department,
        "year_level": year_level,
        "manifesto": manifesto,
    }

    try:
        print(f"[EDIT_CANDIDATE] Updating candidate {candidate_id} with:", update_data)
        supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()
        flash("Candidate updated successfully!", "success")
    except Exception as e:
        flash(f"Could not update candidate: {str(e)}", "error")
        print("[EDIT_CANDIDATE] Error updating candidate:", repr(e))
    return redirect(url_for("admin_dashboard"))


# -------------------- VERIFY USER (ADMIN) --------------------
@app.route("/admin/verify", methods=["POST"])
def admin_verify_user():
    """Admin route to mark a user as verified."""
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))
        
    email = request.form.get("email")
    
    if not email:
        flash("No email provided for verification.", "error")
        return redirect(url_for("admin_dashboard"))
        
    try:
        # Update the 'verified' column in the profiles table
        supabase.table("profiles").update({"verified": True}).eq("email", email).execute()
        flash(f"User {email} verified successfully.", "success")
    except Exception as e:
        flash(f"Failed to verify user: {str(e)}", "error")
        
    return redirect(url_for("admin_dashboard"))


# -------------------- RUN APP --------------------
if __name__ == "__main__":
    app.run(debug=True)