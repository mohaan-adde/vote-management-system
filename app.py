from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import supabase
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# -------------------- HOME --------------------
@app.route("/")
def home():
    if 'user' in session:
        if session['user'] == "admin@gsu.edu":
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('vote'))
    return redirect(url_for('login'))

# -------------------- REGISTER --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            user = supabase.auth.sign_up({"email": email, "password": password})
            flash("✅ Registration successful! Please check your email to verify your account.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"❌ Registration failed: {str(e)}", "error")
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
                flash("✅ Logged in successfully!", "success")
                # Admin-ka horay u ge dashboard
                if user.email == "admin@gsu.edu":
                    return redirect(url_for("admin_dashboard"))
                else:
                    return redirect(url_for("vote"))
            else:
                flash("❌ Invalid credentials or unverified email.", "error")
        except Exception as e:
            msg = str(e)
            if "Invalid login credentials" in msg:
                flash("❌ Incorrect email or password.", "error")
            elif "Email not confirmed" in msg:
                flash("⚠️ Please verify your email before logging in.", "warning")
            else:
                flash("❌ Login failed. Check your internet or Supabase setup.", "error")
        return redirect(url_for("login"))
    return render_template("login.html")

# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    session.clear()
    flash("ℹ️ You have been logged out.", "info")
    return redirect(url_for("home"))

# -------------------- VOTING --------------------
@app.route("/vote")
def vote():
    if 'user' not in session:
        flash("⚠️ Please log in first.", "warning")
        return redirect(url_for("login"))

    # Haddii admin, u diid access vote page
    if session['user'] == "admin@gsu.edu":
        flash("⚠️ Admin cannot vote.", "error")
        return redirect(url_for("admin_dashboard"))

    user_email = session['user']
    candidates, has_voted = [], False
    try:
        candidates = supabase.table("candidates").select("*").execute().data
    except Exception:
        flash("❌ Unable to load candidates.", "error")

    try:
        vote_check = supabase.table("votes").select("id").eq("user_email", user_email).execute().data
        if vote_check:
            has_voted = True
    except Exception:
        pass

    return render_template("vote.html", candidates=candidates, user=user_email, has_voted=has_voted)

@app.route("/vote/<int:candidate_id>", methods=["POST"])
def submit_vote(candidate_id):
    if 'user' not in session:
        flash("⚠️ Please log in first.", "warning")
        return redirect(url_for("login"))

    # Admin-ka ma codeyn karo
    if session['user'] == "admin@gsu.edu":
        flash("⚠️ Admin cannot vote.", "error")
        return redirect(url_for("admin_dashboard"))

    email = session['user']

    try:
        existing = supabase.table("votes").select("id").eq("user_email", email).execute().data
        if existing:
            flash("⚠️ You have already voted!", "error")
            return redirect(url_for("vote"))
    except Exception:
        flash("❌ Error checking your vote status.", "error")
        return redirect(url_for("vote"))

    try:
        supabase.table("votes").insert({"user_email": email, "candidate_id": candidate_id}).execute()
        supabase.rpc("increment_vote", {"cid": candidate_id}).execute()
        flash("🗳️ Your vote has been recorded successfully!", "success")
    except Exception:
        flash("❌ Failed to record your vote.", "error")

    return redirect(url_for("vote"))

# -------------------- RESULTS --------------------
@app.route('/results')
def results():
    try:
        candidates = supabase.table('candidates').select('*').execute().data
        candidates = sorted(candidates, key=lambda x: x['votes'], reverse=True)
    except Exception:
        candidates = []
        flash("❌ Unable to load results.", "error")
    return render_template('results.html', candidates=candidates)

# -------------------- ADMIN DASHBOARD --------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    # Admin check
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("⚠️ Admin access only.", "error")
        return redirect(url_for("login"))

    # Add candidate
    if request.method == "POST":
        name = request.form["name"].strip()
        motto = request.form["motto"].strip()
        photo = request.form.get("photo", "").strip()
        if not photo:
            photo = f"https://placehold.co/150x150/003049/ffffff?text={name[0:2].upper()}"
        try:
            supabase.table("candidates").insert({
                "name": name,
                "motto": motto,
                "photo": photo,
                "votes": 0
            }).execute()
            flash("✅ Candidate added successfully!", "success")
        except Exception as e:
            flash(f"❌ Could not add candidate: {str(e)}", "error")
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

    return render_template("admin_dashboard.html", candidates=candidates, voters=voters)

# -------------------- DELETE CANDIDATE --------------------
@app.route("/admin/delete/<int:candidate_id>")
def delete_candidate(candidate_id):
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("⚠️ Admin access only.", "error")
        return redirect(url_for("login"))
    try:
        supabase.table("candidates").delete().eq("id", candidate_id).execute()
        flash("✅ Candidate deleted successfully!", "success")
    except Exception as e:
        flash(f"❌ Could not delete candidate: {str(e)}", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------- EDIT CANDIDATE --------------------
@app.route("/admin/edit/<int:candidate_id>", methods=["POST"])
def edit_candidate(candidate_id):
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        flash("⚠️ Admin access only.", "error")
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    motto = request.form["motto"].strip()
    photo = request.form.get("photo", "").strip()
    if not photo:
        photo = f"https://placehold.co/150x150/003049/ffffff?text={name[0:2].upper()}"
    try:
        supabase.table("candidates").update({
            "name": name,
            "motto": motto,
            "photo": photo
        }).eq("id", candidate_id).execute()
        flash("✅ Candidate updated successfully!", "success")
    except Exception as e:
        flash(f"❌ Could not update candidate: {str(e)}", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------- RUN APP --------------------
if __name__ == "__main__":
    app.run(debug=True)
