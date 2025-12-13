# Add these routes after the delete_user route

@app.route("/admin/registry/delete/<registry_id>", methods=["POST"])
def delete_registry_entry(registry_id):
    """Delete an entry from student registry."""
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        return redirect(url_for("login"))
    
    try:
        supabase.table("student_registry").delete().eq("id", registry_id).execute()
        flash("Registry entry deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting registry entry: {e}", "error")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/registry/edit/<registry_id>", methods=["POST"])
def edit_registry_entry(registry_id):
    """Edit an entry in student registry."""
    if 'user' not in session or session['user'] != "admin@gsu.edu":
        return redirect(url_for("login"))
    
    try:
        university_id = request.form.get("university_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        
        supabase.table("student_registry").update({
            "university_id": university_id,
            "full_name": full_name,
            "phone": phone
        }).eq("id", registry_id).execute()
        
        flash("Registry entry updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating registry entry: {e}", "error")
    
    return redirect(url_for("admin_dashboard"))
