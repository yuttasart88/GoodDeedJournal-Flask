import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from datetime import datetime, date
from sqlalchemy import func

# --- การตั้งค่าแอปพลิเคชัน ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this_to_a_long_random_string'
basedir = os.path.abspath(os.path.dirname(__file__))
# ตั้งค่าฐานข้อมูล SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'gooddeeds.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- กำหนดสีสำหรับแต่ละหมวดหมู่ (Bootstrap Classes) ---
CATEGORY_COLORS = {
    "สุขภาพ": "bg-success",  # สีเขียว
    "สร้างสรรค์": "bg-warning",  # สีเหลือง
    "การงาน": "bg-primary",  # สีน้ำเงิน
    "ครอบครัว/สังคม": "bg-info",  # สีฟ้าอ่อน
    "เล็กๆน้อยๆ": "bg-secondary",  # สีเทา
}
BOOTSTRAP_COLORS_MAP = {
    "สุขภาพ": "rgba(40, 167, 69, 0.7)",
    "สร้างสรรค์": "rgba(255, 193, 7, 0.7)",
    "การงาน": "rgba(13, 110, 253, 0.7)",
    "ครอบครัว/สังคม": "rgba(13, 202, 240, 0.7)",
    "เล็กๆน้อยๆ": "rgba(108, 117, 125, 0.7)",
}

# --- การตั้งค่าส่วนเสริม (Extensions) ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'


# --- Context Processor: ส่งตัวแปรไปทุกเทมเพลต ---
@app.context_processor
def inject_category_data():
    return dict(
        category_colors=CATEGORY_COLORS,
        bootstrap_colors_map=BOOTSTRAP_COLORS_MAP
    )


# --- การสร้างโมเดลฐานข้อมูล (Database Models) ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    deeds = db.relationship('Deed', backref='author', lazy=True)
    stars = db.relationship('DailyCategoryStar', backref='owner', lazy=True)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class Deed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(300), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class DailyCategoryStar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('date', 'category', 'user_id', name='_date_category_user_uc'),)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- หน้าเว็บ (Routes) ---

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    today = date.today()

    if request.method == 'POST':
        deed_description = request.form.get('description')
        deed_category = request.form.get('category')

        if not deed_category:
            flash('กรุณาเลือกหมวดหมู่', 'danger')
            return redirect(url_for('index'))

        if deed_description and deed_category:
            new_deed = Deed(description=deed_description, category=deed_category, author=current_user)
            db.session.add(new_deed)

            existing_star = DailyCategoryStar.query.filter_by(
                user_id=current_user.id,
                date=today,
                category=deed_category
            ).first()

            if not existing_star:
                new_star = DailyCategoryStar(
                    user_id=current_user.id,
                    date=today,
                    category=deed_category
                )
                db.session.add(new_star)
                flash(f'ยอดเยี่ยม! คุณได้รับดาวหมวดหมู่ "{deed_category}" ⭐️', 'success')
            else:
                flash('บันทึกกิจกรรมสำเร็จ (คุณได้ดาวหมวดหมู่นี้ไปแล้ววันนี้)', 'info')

            db.session.commit()
        return redirect(url_for('index'))

    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    todays_deeds = Deed.query.filter(
        Deed.user_id == current_user.id,
        Deed.date_posted >= today_start,
        Deed.date_posted <= today_end
    ).order_by(Deed.date_posted.desc()).all()

    todays_stars = DailyCategoryStar.query.filter_by(
        user_id=current_user.id,
        date=today
    ).all()

    todays_star_categories = [star.category for star in todays_stars]

    return render_template('index.html', title='วันนี้',
                           deeds=todays_deeds,
                           todays_star_categories=todays_star_categories)


@app.route('/summary')
@login_required
def summary():
    all_stars = DailyCategoryStar.query.filter_by(
        owner=current_user
    ).order_by(DailyCategoryStar.date.asc()).all()

    all_deeds = Deed.query.filter_by(
        author=current_user
    ).order_by(Deed.date_posted.asc()).all()

    # สร้างโครงสร้างข้อมูลสรุปที่รวม "ดาว" และ "กิจกรรม"
    summary_data = {}  # Key: 'YYYY-MM-DD'

    for star in all_stars:
        day_str = star.date.strftime('%Y-%m-%d')
        if day_str not in summary_data:
            summary_data[day_str] = {'stars': [], 'deeds': []}
        summary_data[day_str]['stars'].append(star.category)

    for deed in all_deeds:
        day_str = deed.date_posted.strftime('%Y-%m-%d')
        if day_str not in summary_data:
            summary_data[day_str] = {'stars': [], 'deeds': []}
        summary_data[day_str]['deeds'].append({
            'description': deed.description,
            'category': deed.category,
            'time': deed.date_posted.strftime('%H:%M น.')
        })

    # เตรียมข้อมูลสำหรับกราฟ JS (Weekly/Monthly)
    stars_data_for_js = [
        {'date': star.date.isoformat(), 'category': star.category}
        for star in all_stars
    ]

    return render_template('summary.html', title='สรุปผล',
                           summary_data=summary_data,
                           stars_data_for_js=stars_data_for_js)


@app.route('/dashboard')
@login_required
def dashboard():
    all_stars = DailyCategoryStar.query.filter_by(
        owner=current_user
    ).order_by(DailyCategoryStar.date.asc()).all()

    # 1. ข้อมูลสำหรับกราฟวงกลม (All-Time Category)
    pie_data = {}
    for star in all_stars:
        pie_data[star.category] = pie_data.get(star.category, 0) + 1

    # 2. ข้อมูลสำหรับกราฟเส้น (Cumulative Stars Over Time)
    cumulative_data_js = []
    running_total = 0
    stars_by_day = {}
    for star in all_stars:
        day_str = star.date.isoformat()
        stars_by_day[day_str] = stars_by_day.get(day_str, 0) + 1

    sorted_dates = sorted(stars_by_day.keys())

    for day in sorted_dates:
        running_total += stars_by_day[day]
        cumulative_data_js.append({'x': day, 'y': running_total})

    return render_template('dashboard.html', title='Dashboard',
                           pie_data=pie_data,
                           cumulative_data_js=cumulative_data_js)


# --- หน้าการยืนยันตัวตน (Authentication) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('ชื่อผู้ใช้นี้มีคนใช้แล้ว', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash('สมัครสมาชิกสำเร็จ! กรุณาล็อกอิน', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='สมัครสมาชิก')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('ล็อกอินสำเร็จ!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return render_template('login.html', title='ล็อกอิน')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- คำสั่งสำหรับรันแอป ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)