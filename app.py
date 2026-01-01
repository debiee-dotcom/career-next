from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import firebase_admin
from firebase_admin import credentials, firestore, auth
import google.generativeai as genai
import os, json, re
from dotenv import load_dotenv

from prompt_builder import build_prompt

# 🔹 Load environment variables
load_dotenv()
genai.configure(api_key=os.getenv("api_key"))

# 🔹 Flask app
app = Flask(_name_)
app.secret_key = "supersecretkey"

# 🔹 Firebase setup
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

@app.route("/")
def home():
    return redirect(url_for("login_page"))

# 🔹 SIGNUP PAGE
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        try:
            user = auth.create_user(email=email, password=password, display_name=name)

            db.collection("student").document(user.uid).set({
                "name": name,
                "email": email,
                "aptitude_marks": 0,
                "quiz_answers": {}
            })

            return redirect(url_for("login_page"))
        except Exception as e:
            return render_template("signup.html", error=str(e))

    return render_template("signup.html")

# 🔹 LOGIN PAGE
@app.route("/login_page", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user_query = db.collection("student").where("email", "==", email).limit(1).get()

        if user_query:
            user_doc = user_query[0]
            session["student_id"] = user_doc.id
            return redirect(url_for("quiz_page"))
        else:
            return render_template("login.html", error="Invalid Email or Password")

    return render_template("login.html")

# 🔹 QUIZ PAGE
@app.route("/quiz_page", methods=["GET", "POST"])
def quiz_page():
    if "student_id" not in session:
        return redirect(url_for("login_page"))

    student_id = session["student_id"]

    if request.method == "POST":
        form_data = dict(request.form)

        # Correct answers for aptitude
        correct_answers = {
            "q1": "3 hours",
            "q2": "28",
            "q3": "30°",
            "q4": "Rose",
            "q5": "10 days",
            "q6": "Both (Earth & Heart)"
        }

        aptitude_score = sum(1 for q, ans in correct_answers.items() if form_data.get(q) == ans)

        # Structure data into sections
        structured_data = {
            "Aptitude": {k: form_data.get(k) for k in correct_answers.keys()},
            "Interests": {
                "subject": form_data.get("interests_subject"),
                "project": form_data.get("interests_project"),
                "activity": form_data.get("interests_activity"),
                "career": form_data.get("interests_career"),
                "freetime": form_data.get("interests_freetime")
            },
            "Personality": {
                "role": form_data.get("personality_role"),
                "motivation": form_data.get("personality_motivation"),
                "quality": form_data.get("personality_quality"),
                "workstyle": form_data.get("personality_workstyle"),
                "inspiration": form_data.get("personality_inspiration")
            },
            "Academic & Future Plans": {
                "score": form_data.get("academic_score"),
                "best_subject": form_data.get("academic_best_subject"),
                "future": form_data.get("academic_future"),
                "priority": form_data.get("academic_priority")
            },
            "Additional Info": {
                "annual_income": form_data.get("annual_income"),
                "city": form_data.get("city")
            }
        }

        db.collection("student").document(student_id).set({
            "quiz_answers": structured_data,
            "aptitude_marks": aptitude_score
        }, merge=True)

        return redirect(url_for("results", student_id=student_id))

    return render_template("quiz.html")

# 🔹 RESULTS PAGE (Runs AI)
@app.route("/results/<student_id>")
def results(student_id):
    student_ref = db.collection("student").document(student_id)
    doc = student_ref.get()

    if not doc.exists:
        return "Student not found", 404

    student_data = doc.to_dict()
    prompt = build_prompt(student_data)

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)

    ai_text = response.text.strip()
    print("DEBUG - Raw Gemini Response:\n", ai_text)

    # Clean Gemini response
    ai_text_clean = ai_text.replace("json", "").replace("", "").strip()

    # Extract JSON
    json_match = re.search(r"\{[\s\S]*\}", ai_text_clean)
    if json_match:
        json_text = json_match.group(0)
    else:
        json_text = ai_text_clean

    try:
        ai_result = json.loads(json_text)
    except Exception as e:
        ai_result = {"raw_response": ai_text_clean, "parse_error": str(e)}

    student_ref.set({"ai_results": ai_result}, merge=True)

    return render_template("results.html", student=student_data, ai=ai_result)

# -------------------------------------------------
# MAIN
# -------------------------------------------------
if _name_ == "_main_":
    app.run(port=5000, debug=True)