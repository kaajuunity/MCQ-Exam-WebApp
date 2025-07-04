import pandas as pd
import random
from extensions import mail
from flask_mail import Message
from flask import current_app

def send_otp_email(email, otp):
    msg = Message('Your OTP Code', sender=current_app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = f'Your OTP is: {otp}'
    mail.send(msg)

def generate_otp():
    return str(random.randint(100000, 999999))

def load_questions_from_excel(filepath='questions.xlsx'):
    df = pd.read_excel(filepath)
    questions = []
    for _, row in df.iterrows():
        questions.append({
            'question': row['question'],
            'options': {
                'a': row['a'],
                'b': row['b'],
                'c': row['c'],
                'd': row['d'],
            },
            'answer': row['correct'].lower()
        })
    return questions

def classify_role(score):
    if score < 50:
        return 'Fail'
    elif score < 60:
        return 'QA'
    elif score < 70:
        return 'DBMS'
    else:
        return 'AI DevOps'

def send_password_reset_otp(email, otp):
    msg = Message("Your OTP for Password Reset",
                  sender="noreply@example.com",
                  recipients=[email])
    msg.body = f"Your OTP for password reset is: {otp}"
    mail.send(msg)
