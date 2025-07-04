class Config:
    SECRET_KEY = 'your-secret-key'

    SQLALCHEMY_DATABASE_URI = 'sqlite:///exam.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail setup
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'im2aaditya@gmail.com'
    MAIL_PASSWORD = 'wpnmltyjenjikhiy'

    ADMIN_EMAIL = 'admin@orbiqe.com'
    ADMIN_PASSWORD = 'admin123#'  # Or better: use hashed password later
