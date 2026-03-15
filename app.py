import os, json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tiffin-physics-super-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tiffin_cpac.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'home'

# --- MODELS ---
class Teacher(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(10), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    @property
    def role(self):
        return 'teacher'
    def get_id(self):
        return f"teacher_{self.id}"

class Cohort(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_year = db.Column(db.Integer, nullable=False)
    end_year = db.Column(db.Integer, nullable=False)
    students = db.relationship('Student', backref='cohort', lazy=True)

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    cohort_id = db.Column(db.Integer, db.ForeignKey('cohort.id'), nullable=False)

    @property
    def role(self):
        return 'student'
    def get_id(self):
        return f"student_{self.id}"

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False)

class Practical(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

practical_skills = db.Table('practical_skills',
    db.Column('practical_id', db.Integer, db.ForeignKey('practical.id'), primary_key=True),
    db.Column('skill_id', db.Integer, db.ForeignKey('skill.id'), primary_key=True)
)
Practical.skills = db.relationship('Skill', secondary=practical_skills, lazy='subquery', backref=db.backref('practicals', lazy=True))

class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    practical_id = db.Column(db.Integer, db.ForeignKey('practical.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    date_signed = db.Column(db.DateTime, default=datetime.utcnow)

# --- AUTH & ACCESS CONTROL ---
@login_manager.user_loader
def load_user(user_id):
    if user_id.startswith('teacher_'):
        return Teacher.query.get(int(user_id.split('_')[1]))
    elif user_id.startswith('student_'):
        return Student.query.get(int(user_id.split('_')[1]))
    return None

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- UTILS ---
def get_academic_end_year():
    now = datetime.utcnow()
    return now.year if now.month < 9 else now.year + 1

def get_cohort_title(end_year):
    acad_end = get_academic_end_year()
    if end_year == acad_end: return "Year 13"
    elif end_year == acad_end + 1: return "Year 12"
    elif end_year < acad_end:
        diff = acad_end - end_year
        return "Left last year" if diff == 1 else f"Left {diff} years ago"
    return f"Future (Starts {end_year-2})"

# --- ROUTES ---
@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role == 'teacher': return redirect(url_for('dashboard'))
        else: return redirect(url_for('student_view', id=current_user.id))
    return render_template('home.html')

@app.route('/login/student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        fname = request.form.get('first_name').strip()
        lname = request.form.get('last_name').strip()
        year_group = int(request.form.get('year_group'))
        
        target_end_year = get_academic_end_year() if year_group == 13 else get_academic_end_year() + 1
        
        student = Student.query.join(Cohort).filter(
            Student.first_name.ilike(fname),
            Student.last_name.ilike(lname),
            Cohort.end_year == target_end_year
        ).first()

        if student:
            login_user(student)
            return redirect(url_for('student_view', id=student.id))
        
        flash('Student not found. Please check your spelling and year group.', 'error')
    return render_template('login_student.html')

@app.route('/login/teacher', methods=['GET', 'POST'])
def login_teacher():
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        user = Teacher.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login_teacher.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        title = request.form.get('title')
        fname = request.form.get('first_name').strip()
        lname = request.form.get('last_name').strip()
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')

        if not email.endswith('@tiffin.kingston.sch.uk'):
            flash('Error: Must use a @tiffin.kingston.sch.uk email address.', 'error')
            return redirect(url_for('register'))
        
        if email.split('@')[0].isdigit():
            flash('Error: Email prefix cannot consist solely of numbers.', 'error')
            return redirect(url_for('register'))

        if Teacher.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))

        new_user = Teacher(email=email, title=title, first_name=fname, last_name=lname, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login_teacher'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@teacher_required
def dashboard():
    cohorts = Cohort.query.order_by(Cohort.end_year.desc()).all()
    cohort_data = [{'id': c.id, 'title': get_cohort_title(c.end_year), 'years': f"{c.start_year}-{c.end_year}", 'student_count': len(c.students)} for c in cohorts]
    return render_template('dashboard.html', cohorts=cohort_data)

@app.route('/cohort/add', methods=['POST'])
@teacher_required
def add_cohort():
    db.session.add(Cohort(start_year=int(request.form.get('start_year')), end_year=int(request.form.get('end_year'))))
    db.session.commit()
    flash('Cohort added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/cohort/<int:id>')
@teacher_required
def cohort_view(id):
    cohort = Cohort.query.get_or_404(id)
    practicals, all_skills = Practical.query.all(), Skill.query.all()
    matrix = [{'id': p.id, 'name': p.name, 'skills': [s.name for s in p.skills]} for p in practicals]

    students_data = []
    for s in cohort.students:
        assessments = Assessment.query.filter_by(student_id=s.id).all()
        skill_totals = {sk.name: 0 for sk in all_skills}
        prac_totals = {p.id: 0 for p in practicals}
        assessed_cells = {p.id: {} for p in practicals}
        
        for a in assessments:
            sk_name = Skill.query.get(a.skill_id).name
            skill_totals[sk_name] += 1
            prac_totals[a.practical_id] += 1
            assessed_cells[a.practical_id][sk_name] = True
            
        status = "Fail" if any(count < 3 for count in skill_totals.values()) else "Pass"
        students_data.append({'id': s.id, 'first_name': s.first_name, 'last_name': s.last_name, 'total_ticks': len(assessments), 'status': status, 'skill_totals': skill_totals, 'prac_totals': prac_totals, 'assessed_cells': assessed_cells})

    return render_template('cohort.html', cohort=cohort, title=get_cohort_title(cohort.end_year), matrix=json.dumps(matrix), students_json=json.dumps(students_data), prac_names=json.dumps({p.id: p.name for p in practicals}))

@app.route('/cohort/<int:id>/add_student', methods=['POST'])
@teacher_required
def add_student(id):
    db.session.add(Student(first_name=request.form.get('first_name').strip(), last_name=request.form.get('last_name').strip(), cohort_id=id))
    db.session.commit()
    flash('Student added.', 'success')
    return redirect(url_for('cohort_view', id=id))

@app.route('/cohort/<int:id>/bulk_add', methods=['POST'])
@teacher_required
def bulk_add(id):
    format_type = request.form.get('format')
    data = request.form.get('students_data').strip().split('\n')
    for line in data:
        line = line.strip()
        if not line: continue
        fname, lname = "", ""
        if format_type == "First, Last":
            parts = line.split(',')
            if len(parts) >= 2: fname, lname = parts[0].strip(), parts[1].strip()
        elif format_type == "Last, First":
            parts = line.split(',')
            if len(parts) >= 2: lname, fname = parts[0].strip(), parts[1].strip()
        elif format_type == "Last First":
            parts = line.split()
            if len(parts) >= 2: lname, fname = parts[0], " ".join(parts[1:])
        if fname and lname:
            db.session.add(Student(first_name=fname, last_name=lname, cohort_id=id))
    db.session.commit()
    flash('Bulk students added successfully.', 'success')
    return redirect(url_for('cohort_view', id=id))

@app.route('/student/<int:id>')
@login_required
def student_view(id):
    if current_user.role == 'student' and current_user.id != id: abort(403)
    student = Student.query.get_or_404(id)
    assessments = Assessment.query.filter_by(student_id=student.id).all()
    
    prac_scores = {p: 0 for p in Practical.query.all()}
    skill_scores = {sk: 0 for sk in Skill.query.all()}
    
    for a in assessments:
        prac_scores[Practical.query.get(a.practical_id)] += 1
        skill_scores[Skill.query.get(a.skill_id)] += 1
        
    return render_template('student.html', student=student, prac_scores=prac_scores, skill_scores=skill_scores, total_score=len(assessments), date=datetime.utcnow().strftime('%d/%m/%Y'))

@app.route('/grade/<int:student_id>/<int:prac_id>', methods=['GET', 'POST'])
@login_required
def grade(student_id, prac_id):
    if current_user.role == 'student' and current_user.id != student_id: abort(403)
    student = Student.query.get_or_404(student_id)
    practical = Practical.query.get_or_404(prac_id)
    skills = practical.skills
    
    if request.method == 'POST' and current_user.role == 'teacher':
        for sk in skills:
            achieved = request.form.get(f'skill_{sk.id}') == 'on'
            existing = Assessment.query.filter_by(student_id=student.id, skill_id=sk.id, practical_id=practical.id).first()
            if achieved and not existing:
                db.session.add(Assessment(student_id=student.id, skill_id=sk.id, practical_id=practical.id, teacher_id=current_user.id))
            elif not achieved and existing:
                db.session.delete(existing)
        db.session.commit()
        flash('Updated Successfully', 'success')
        return redirect(url_for('cohort_view', id=student.cohort_id))

    assessments = Assessment.query.filter_by(student_id=student.id, practical_id=practical.id).all()
    assessed_skill_ids = {a.skill_id: a for a in assessments}
    signatures = {a.skill_id: f"{Teacher.query.get(a.teacher_id).first_name[0]} {Teacher.query.get(a.teacher_id).last_name} ({a.date_signed.strftime('%d/%m/%Y')})" for a in assessments}

    return render_template('grade.html', student=student, practical=practical, skills=skills, assessed=assessed_skill_ids, signatures=signatures)

# --- SEEDING ---
def seed_database():
    with app.app_context():
        db.create_all()
        if not Skill.query.first():
            # 1. Seed exact 11 skills
            skill_definitions = {
                '1a': "Correctly follows written instructions to carry out experimental techniques or procedures.",
                '2a': "Correctly uses appropriate instrumentation, apparatus and materials (including ICT) to carry out investigative activities, experimental techniques and procedures with minimal assistance or prompting.",
                '2b': "Carries out techniques or procedures methodically, in sequence and in combination, identifying practical issues and making adjustments where necessary.",
                '2c': "Identifies and controls significant quantitative variables where applicable, and plans approaches to take account of variables that cannot readily be controlled.",
                '2d': "Selects appropriate equipment and measurement strategies in order to ensure suitably accurate results.",
                '3a': "Identifies hazards and assesses risks associated with these hazards, making safety adjustments as necessary, when carrying out experimental techniques and procedures in the lab or field.",
                '3b': "Uses appropriate safety equipment and approaches to minimise risks with minimal prompting.",
                '4a': "Makes accurate observations relevant to the experimental or investigative procedure.",
                '4b': "Obtains accurate, precise and sufficient data for experimental and investigative procedures and records this methodically using appropriate units and conventions.",
                '5a': "Uses appropriate software and/or tools to process data, carry out research and report findings.",
                '5b': "Cites sources of information demonstrating that research has taken place, supporting planning and conclusions."
            }
            skill_objs = {}
            for k, v in skill_definitions.items():
                s = Skill(name=k, description=v)
                db.session.add(s)
                skill_objs[k] = s
            db.session.commit()

            # 2. Seed 16 Practicals and mappings
            practical_mappings = [
                ("1. Stationary Waves", ['1a', '2c', '3a', '3b', '4a', '4b']),
                ("2.a Young's slit", ['2a', '2b', '3a', '3b', '4a', '4b']),
                ("2.b Diffraction Gratings", ['2a', '2b', '2c', '2d', '4a', '4b']),
                ("3. Determination of g", ['1a', '2a', '2d', '4b', '5a', '5b']),
                ("4. Young modulus", ['1a', '2c', '2d', '3b', '4a', '5a', '5b']),
                ("5. Resistivity of a wire", ['2a', '2c', '3b', '4a', '5a', '5b']),
                ("6. emf", ['2a', '2c', '3b', '4a', '5a', '5b']),
                ("7.a SHM - Simple Pendulum", ['1a', '2a', '2b', '4b', '5a', '5b']),
                ("7.b SHM - Mass spring", ['1a', '2a', '2b', '4b']),
                ("8.a Boyle's Law", ['1a', '2b', '2c', '2d', '3a', '4b']),
                ("8b Charles' Law", ['1a', '2c', '3a', '3b', '4a', '5a', '5b']),
                ("9.a Capacitor Discharging", ['1a', '2c', '2d', '3a', '3b', '4a']),
                ("9.b Capacitor Charging", ['1a', '3b', '4a', '4b']),
                ("10. Motor Effect", ['2b', '2d', '3a', '3b', '4a', '4b']),
                ("11. Search Coils", ['1a', '2a', '2c', '2d', '4b']),
                ("12. Gamma Radiation", ['1a', '2b', '2d', '3a', '3b', '4a', '4b'])
            ]
            
            for p_name, s_keys in practical_mappings:
                p = Practical(name=p_name)
                for sk in s_keys:
                    p.skills.append(skill_objs[sk])
                db.session.add(p)
            db.session.commit()

if __name__ == '__main__':
    seed_database()
    app.run(debug=True, port=5000)