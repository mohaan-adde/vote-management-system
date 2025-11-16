from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import supabase
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Storage bucket for candidate photos (create this bucket in Supabase and make it public)
BUCKET_NAME = os.getenv("CANDIDATE_BUCKET", "candidate-photos")


def get_election_end():
    """Return election end timestamp string in ISO format (or None if not set)."""
    try:
        data = (
            supabase.table("settings").select("election_end").limit(1).single().execute().data
        )
        return data.get("election_end") if data else None
    except Exception:
        return None


def election_is_active(now_dt=None):
    end_iso = get_election_end()
    if not end_iso:
        return True
    try:
        # Normalize Z to +00:00 for fromisoformat
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        now_dt = now_dt or datetime.now(timezone.utc)
        return now_dt < end_dt
    except Exception:
        return True


def is_user_verified(email: str) -> bool:
    try:
        row = supabase.table("profiles").select("verified").eq("email", email).single().execute().data
        return bool(row and row.get("verified"))
    except Exception:
        return False

# -------------------- HOME --------------------
@app.route("/")
def home():
    # Always show landing page (even when logged in)
    candidates = []
    votes = []
    profiles = []

    try:
        candidates = supabase.table("candidates").select("id,name,photo,votes").execute().data or []
    except Exception:
        candidates = []

    try:
        votes = supabase.table("votes").select("id").execute().data or []
    except Exception:
        votes = []

    try:
        profiles = supabase.table("profiles").select("id").execute().data or []
    except Exception:
        profiles = []

    try:
        candidates_sorted = sorted(candidates, key=lambda x: x.get("votes", 0) or 0, reverse=True)
    except Exception:
        candidates_sorted = candidates

    top_candidates = candidates_sorted[:3]

    total_registered = len(profiles)
    total_voted = len(votes)
    max_votes = max((c.get("votes", 0) or 0) for c in candidates) if candidates else 0
    turnout = int(round((total_voted * 100) / total_registered)) if total_registered else 0

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
    if request.method == "POST":
        # Support either a single full name field or separate first/last name fields
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        name = request.form.get("name", "").strip()
        if not name:
            name = (first_name + " " + last_name).strip()
        university_id = request.form.get("university_id", "").strip()
        email = request.form["email"]
        password = request.form["password"]
        try:
            response = supabase.auth.sign_up({"email": email, "password": password})
            try:
                supabase.table("profiles").insert({
                    "email": email,
                    "name": name,
                    "university_id": university_id,
                    "verified": False
                }).execute()
            except Exception:
                pass
            flash("Registration successful. Check your email to confirm your account. After confirming, please wait for admin verification before voting.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"Registration failed: {str(e)}", "error")
    return render_template("register.html")

# -------------------- LOGIN --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user = response.user
            if user:
                session["user"] = user.email
                session["user_id"] = user.id
                flash("Logged in successfully.", "success")
                if user.email == "admin@gsu.edu":
                    return redirect(url_for("admin_dashboard"))
                # Ensure profile exists
                try:
                    prof = supabase.table("profiles").select("verified").eq("email", user.email).single().execute().data
                except Exception:
                    prof = None
                if not prof:
                    try:
                        supabase.table("profiles").insert({"email": user.email, "verified": False}).execute()
                    except Exception:
                        pass
                if not is_user_verified(user.email):
                    return redirect(url_for("pending_verification"))
                return redirect(url_for("vote"))
            else:
                flash("Invalid credentials or unverified email.", "error")
        except Exception as e:
            msg = str(e)
            if "Invalid login credentials" in msg:
                flash("Incorrect email or password.", "error")
            elif "Email not confirmed" in msg:
                flash("Please verify your email before logging in.", "warning")
            else:
                flash("Login failed. Check your internet or Supabase setup.", "error")
        return redirect(url_for("login"))
    return render_template("login.html")

# -------------------- FORGOT PASSWORD --------------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your email address.", "warning")
            return redirect(url_for("forgot_password"))
        try:
            redirect_url = url_for("update_password", _external=True)
            supabase.auth.reset_password_for_email(email, options={"redirect_to": redirect_url})
            flash("If that email exists, a password reset link has been sent.", "info")
        except Exception as e:
            flash("Could not send password reset email. Please try again later.", "error")
        return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/update-password", methods=["GET", "POST"])
def update_password():
    """Handle password update after the user clicks the email reset link.

    Supabase will create a session for the user in the browser when they
    open the reset link. Here we just ask for a new password and send it
    to Supabase.
    """
    if request.method == "POST":
        new_password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()
        if not new_password or not confirm:
            flash("Please fill in both password fields.", "warning")
            return redirect(url_for("update_password"))
        if new_password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("update_password"))
        try:
            supabase.auth.update_user({"password": new_password})
            flash("Your password has been updated. You can now log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            flash("Could not update password. The reset link may have expired.", "error")
            return redirect(url_for("login"))

    return render_template("update_password.html")

# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
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
    return render_template("pending_verification.html")

# -------------------- VOTING --------------------
@app.route("/vote")
def vote():
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    # Haddii admin, u diid access vote page
    if session['user'] == "admin@gsu.edu":
        flash("Admin cannot vote.", "error")
        return redirect(url_for("admin_dashboard"))

    user_email = session['user']
    if not is_user_verified(user_email):
        flash("Your account is pending admin verification.", "warning")
        return redirect(url_for("pending_verification"))

    candidates, has_voted = [], False
    try:
        candidates = supabase.table("candidates").select("*").execute().data
    except Exception:
        flash("Unable to load candidates.", "error")

    try:
        vote_check = supabase.table("votes").select("id").eq("user_email", user_email).execute().data
        if vote_check:
            has_voted = True
    except Exception:
        pass

    try:
        candidates = sorted(candidates, key=lambda x: x.get('votes', 0), reverse=True)
    except Exception:
        pass

    return render_template("vote.html", candidates=candidates, user=user_email, has_voted=has_voted, election_end_iso=get_election_end())

@app.route("/vote/<int:candidate_id>", methods=["POST"])
def submit_vote(candidate_id):
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    # Admin-ka ma codeyn karo
    if session['user'] == "admin@gsu.edu":
        flash("Admin cannot vote.", "error")
        return redirect(url_for("admin_dashboard"))

    email = session['user']

    if not election_is_active():
        flash("Voting period has ended.", "warning")
        return redirect(url_for("vote"))

    try:
        existing = supabase.table("votes").select("id").eq("user_email", email).execute().data
        if existing:
            flash("You have already voted!", "error")
            return redirect(url_for("vote"))
    except Exception:
        flash("Error checking your vote status.", "error")
        return redirect(url_for("vote"))

    try:
        supabase.table("votes").insert({"user_email": email, "candidate_id": candidate_id}).execute()
        supabase.rpc("increment_vote", {"cid": candidate_id}).execute()
        flash("Your vote has been recorded successfully!", "success")
    except Exception:
        flash("Failed to record your vote.", "error")

    return redirect(url_for("vote"))

# -------------------- RESULTS --------------------
@app.route('/results')
def results():
    try:
        candidates = supabase.table('candidates').select('*').execute().data
        candidates = sorted(candidates, key=lambda x: x['votes'], reverse=True)
    except Exception:
        candidates = []
        flash("Unable to load results.", "error")
    return render_template('results.html', candidates=candidates)

# -------------------- ADMIN DASHBOARD --------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    # Admin check
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    # Handle POST actions
    if request.method == "POST":
        action = request.form.get("action", "add_candidate")

        if action == "add_candidate":
            name = request.form["name"].strip()
            motto = request.form["motto"].strip()
            photo = request.form.get("photo", "").strip()
            bio = request.form.get("bio", "").strip()
            department = request.form.get("department", "").strip()
            year_level = request.form.get("year_level", "").strip()
            manifesto = request.form.get("manifesto", "").strip()

            # Try upload to Supabase Storage if a file is provided
            file = request.files.get("photo_file")
            if file and file.filename:
                try:
                    ext = os.path.splitext(file.filename)[1].lower()
                    fname = f"candidate_{int(time.time())}_{secure_filename(name)}{ext}"
                    file_bytes = file.read()
                    print("[ADD_CANDIDATE] Uploading photo to bucket", BUCKET_NAME, "as", fname)
                    supabase.storage.from_(BUCKET_NAME).upload(fname, file_bytes, {"content-type": file.mimetype, "upsert": True})
                    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(fname)
                    if isinstance(public_url, dict):
                        data = public_url.get("data") or {}
                        photo = (
                            data.get("publicUrl")
                            or public_url.get("publicUrl")
                            or public_url.get("public_url")
                            or photo
                        )
                    elif isinstance(public_url, str):
                        photo = public_url
                    # Final fallback: construct URL
                    if not photo:
                        base = os.getenv("SUPABASE_URL", "").rstrip("/")
                        if base:
                            photo = f"{base}/storage/v1/object/public/{BUCKET_NAME}/{fname}"
                    if not photo:
                        flash("Photo uploaded but public URL could not be determined.", "warning")
                        print("[ADD_CANDIDATE] Could not determine public URL from", public_url)
                except Exception as e:
                    flash("Failed to upload candidate photo to Supabase. Check server logs.", "error")
                    print("[ADD_CANDIDATE] Error uploading photo:", repr(e))

            if not photo:
                photo = f"https://placehold.co/150x150/003049/ffffff?text={name[0:2].upper()}"
            try:
                insert_payload = {
                    "name": name,
                    "motto": motto,
                    "photo": photo,
                    "bio": bio,
                    "department": department,
                    "year_level": year_level,
                    "manifesto": manifesto,
                    "votes": 0,
                }
                print("[ADD_CANDIDATE] Inserting candidate:", insert_payload)
                result = supabase.table("candidates").insert(insert_payload).execute()
                print("[ADD_CANDIDATE] Insert result:", getattr(result, "data", result))
                flash("Candidate added successfully!", "success")
            except Exception as e:
                flash(f"Could not add candidate: {str(e)}", "error")
                print("[ADD_CANDIDATE] Error inserting candidate:", repr(e))
            return redirect(url_for("admin_dashboard"))

        if action == "update_settings":
            election_end = request.form.get("election_end", "").strip()
            try:
                # Try upsert, fall back to insert
                try:
                    supabase.table("settings").upsert({"id": 1, "election_end": election_end}).execute()
                except Exception:
                    try:
                        supabase.table("settings").delete().eq("id", 1).execute()
                    except Exception:
                        pass
                    supabase.table("settings").insert({"id": 1, "election_end": election_end}).execute()
                flash("Election end time updated.", "success")
            except Exception as e:
                flash(f"Failed to update settings: {str(e)}", "error")
            return redirect(url_for("admin_dashboard"))

    # Get candidates
    try:
        candidates = supabase.table("candidates").select("*").execute().data
    except Exception:
        candidates = []

    # Get voters
    try:
        votes = supabase.table("votes").select("*").execute().data
        voters = []
        for v in votes:
            candidate = supabase.table("candidates").select("name").eq("id", v["candidate_id"]).single().execute().data
            voters.append({
                "user_email": v["user_email"],
                "candidate_name": candidate["name"] if candidate else "Unknown",
                "voted_at": v["voted_at"]
            })
    except Exception:
        voters = []

    # Get profiles
    try:
        profiles = supabase.table("profiles").select("email,name,university_id,verified").execute().data
    except Exception:
        profiles = []

    return render_template("admin_dashboard.html", candidates=candidates, voters=voters, profiles=profiles, election_end_iso=get_election_end())

# -------------------- DELETE CANDIDATE --------------------
@app.route("/admin/delete/<int:candidate_id>")
def delete_candidate(candidate_id):
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))
    try:
        supabase.table("candidates").delete().eq("id", candidate_id).execute()
        flash("Candidate deleted successfully!", "success")
    except Exception as e:
        flash(f"Could not delete candidate: {str(e)}", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------- EDIT CANDIDATE --------------------
@app.route("/admin/edit/<int:candidate_id>", methods=["POST"])
def edit_candidate(candidate_id):
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    motto = request.form["motto"].strip()
    photo = request.form.get("photo", "").strip()
    bio = request.form.get("bio", "").strip()
    department = request.form.get("department", "").strip()
    year_level = request.form.get("year_level", "").strip()
    manifesto = request.form.get("manifesto", "").strip()

    file = request.files.get("photo_file")
    if file and file.filename:
        try:
            ext = os.path.splitext(file.filename)[1].lower()
            fname = f"candidate_{int(time.time())}_{secure_filename(name)}{ext}"
            file_bytes = file.read()
            print("[EDIT_CANDIDATE] Uploading photo to bucket", BUCKET_NAME, "as", fname)
            supabase.storage.from_(BUCKET_NAME).upload(fname, file_bytes, {"content-type": file.mimetype, "upsert": True})
            public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(fname)
            if isinstance(public_url, dict):
                data = public_url.get("data") or {}
                photo = (
                    data.get("publicUrl")
                    or public_url.get("publicUrl")
                    or public_url.get("public_url")
                    or photo
                )
            elif isinstance(public_url, str):
                photo = public_url
            if not photo:
                base = os.getenv("SUPABASE_URL", "").rstrip("/")
                if base:
                    photo = f"{base}/storage/v1/object/public/{BUCKET_NAME}/{fname}"
            if not photo:
                flash("Photo uploaded but public URL could not be determined.", "warning")
                print("[EDIT_CANDIDATE] Could not determine public URL from", public_url)
        except Exception as e:
            flash("Failed to upload candidate photo to Supabase. Check server logs.", "error")
            print("[EDIT_CANDIDATE] Error uploading photo:", repr(e))

    if not photo:
        photo = f"https://placehold.co/150x150/003049/ffffff?text={name[0:2].upper()}"

    update_data = {
        "name": name,
        "motto": motto,
        "photo": photo,
        "bio": bio,
        "department": department,
        "year_level": year_level,
        "manifesto": manifesto,
    }

    try:
        print(f"[EDIT_CANDIDATE] Updating candidate {candidate_id} with:", update_data)
        result = supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()
        print("[EDIT_CANDIDATE] Update result:", getattr(result, "data", result))
        flash("Candidate updated successfully!", "success")
    except Exception as e:
        flash(f"Could not update candidate: {str(e)}", "error")
        print("[EDIT_CANDIDATE] Error updating candidate:", repr(e))
    return redirect(url_for("admin_dashboard"))


# -------------------- VERIFY USER (ADMIN) --------------------
@app.route("/admin/verify", methods=["POST"])
def admin_verify_user():
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("Admin access only.", "error")
        return redirect(url_for("login"))
    email = request.form.get("email")
    if not email:
        return redirect(url_for("admin_dashboard"))
    try:
        supabase.table("profiles").update({"verified": True}).eq("email", email).execute()
        flash("User verified.", "success")
    except Exception as e:
        flash(f"Failed to verify user: {str(e)}", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------- RUN APP --------------------
if __name__ == "__main__":
    app.run(debug=True)
