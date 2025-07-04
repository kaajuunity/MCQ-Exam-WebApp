import os
import random
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Response
from config import Config
from extensions import db, mail
from models import User, Result
from helpers import send_otp_email, generate_otp, load_questions_from_excel, classify_role

from flask import make_response, render_template
from xhtml2pdf import pisa
from io import BytesIO
import datetime

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail.init_app(app)

# ========== ROUTES ==========

@app.route('/')
def home():
    return render_template('register.html')

# Register with OTP
@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    existing = User.query.filter_by(email=email).first()
    if existing:
        flash("Email already registered. Please login.")
        return redirect(url_for('login'))

    otp = generate_otp()
    user = User(email=email, otp=otp)
    db.session.add(user)
    db.session.commit()
    send_otp_email(email, otp)
    session['email'] = email
    return redirect(url_for('verify_otp'))

# OTP Verification and Password Set
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        email = session.get('email')
        otp_input = request.form['otp']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and user.otp == otp_input:
            user.set_password(password)
            user.otp_verified = True
            db.session.commit()
            flash("OTP verified. Please login.")
            return redirect(url_for('login'))
        else:
            flash("Invalid OTP.")
    return render_template('verify_otp.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and user.otp_verified and user.check_password(password):
            if user.attempted:
                return render_template("already_attempted.html")
            session['email'] = email
            return redirect(url_for('test'))
        else:
            flash("Invalid credentials or unverified account.")
    return render_template('login.html')

# Start Test
@app.route('/test')
def test():
    email = session.get('email')
    if not email:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if user and user.attempted:
        flash('You have already attempted the test.')
        return render_template('already_attempted.html')

    # ✅ Generate fresh questions
    all_questions = load_questions_from_excel()
    sample_size = min(40, len(all_questions))
    selected_questions = random.sample(all_questions, sample_size)

    # ✅ Save to session for test flow
    session['questions'] = selected_questions
    session['start_time'] = time.time()

    return render_template('quiz.html', questions=selected_questions, time_limit=2400)

# Submit Test
@app.route('/submit', methods=['POST'])
def submit():
    email = session.get('email')
    if not email:
        return redirect(url_for('login'))

    cheated = request.form.get('cheated') == 'true'
    submitted_answers = request.form
    questions = session.get('questions', [])
    
    correct = 0
    for idx, q in enumerate(questions):
        qid = f'q{idx}'
        user_ans = submitted_answers.get(qid, '').lower()
        if user_ans == q['answer']:
            correct += 1

    score = int((correct / len(questions)) * 100)
    role = classify_role(score)

    # Force override if cheating
    if cheated:
        role = "Disqualified for Cheating"
        score = 0
        correct = 0

    # Mark user as attempted
    user = User.query.filter_by(email=email).first()
    user.attempted = True
    db.session.commit()

    # Save result
    result = Result(email=email, score=score, correct=correct, role=role)
    db.session.add(result)
    db.session.commit()

    return render_template("result.html", score=score, role=role, correct=correct, total=len(questions))

@app.route('/download-pdf')
def download_pdf():
    email = session.get('email')
    result = Result.query.filter_by(email=email).order_by(Result.id.desc()).first()

    if not result:
        return "Result not found"

    html = render_template("result_pdf.html", 
        email=email,
        score=result.score,
        correct=result.correct,
        # correct=int(result.score * 40 / 100),
        total=40,
        role=result.role,
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=result.pdf'
    return response

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Admin Login
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == Config.ADMIN_EMAIL and password == Config.ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid admin credentials.")
    return render_template('admin_login.html')

# Admin Dashboard
@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    users = User.query.all()
    results = Result.query.all()
    return render_template('admin.html', users=users, results=results)

# Admin: Reset student status
@app.route('/admin/reset/<int:user_id>')
def admin_reset(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    user = User.query.get(user_id)
    if user:
        user.attempted = False
        db.session.commit()
        flash(f"Reset attempt status for {user.email}")
    return redirect(url_for('admin_dashboard'))

# Admin: Download all results as CSV
@app.route('/admin/download-results')
def download_all_results():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    import csv
    from flask import Response
    results = Result.query.all()

    si = BytesIO()
    si.write("Email,Score,Role\n".encode())

    for r in results:
        line = f"{r.email},{r.score},{r.role}\n"
        si.write(line.encode())

    si.seek(0)
    return Response(
        si,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=all_results.csv'}
    )

@app.route('/admin/download/<int:user_id>', endpoint='download_user_result')
def download_user_result(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    user = User.query.get(user_id)
    result = Result.query.filter_by(email=user.email).order_by(Result.id.desc()).first()

    if not result:
        return "Result not found"

    html = render_template("result_pdf.html",
        email=user.email,
        score=result.score,
        correct=result.correct,
        # correct=int(result.score * 40 / 100),
        total=40,
        role=result.role,
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={user.email}_result.pdf'
    return response

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            otp = generate_otp()
            user.otp = otp
            db.session.commit()
            send_otp_email(email, otp)
            session['reset_email'] = email
        # ✅ Use generic flash message regardless of user existence
        flash("If this email is registered, you'll receive an OTP.")
        return redirect(url_for('reset_verify_otp'))
    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if not session.get('otp_verified_for_reset'):
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for('reset_password'))

        email = session.get('reset_email')
        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(new_password)
            user.otp = None
            db.session.commit()
            session.pop('otp_verified_for_reset', None)
            session.pop('reset_email', None)
            flash("Password reset successful. Please log in.")
            return redirect(url_for('login'))

    return render_template('reset_password.html')


@app.route('/reset-verify-otp', methods=['GET', 'POST'])
def reset_verify_otp():
    if request.method == 'POST':
        email = session.get('reset_email')
        otp_input = request.form['otp']
        user = User.query.filter_by(email=email).first()

        if user and user.otp == otp_input:
            session['otp_verified_for_reset'] = True
            return redirect(url_for('reset_password'))
        else:
            flash("Invalid OTP. Please try again.")
    
    return render_template('reset_verify_otp.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
