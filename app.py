from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from flask import session
from flask_babel import Babel, gettext as _
from flask_migrate import Migrate

# 初始化 Flask 应用
app = Flask(__name__)
app.secret_key = 'supersecretkey'

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Migrate 必须在 db 初始化后再绑定 app

# 配置文件上传目录
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 配置 Flask-Babel
app.config['BABEL_DEFAULT_LOCALE'] = 'zh'
babel = Babel(app)

def get_locale():
    return session.get('lang', 'zh')

babel.init_app(app, locale_selector=get_locale)

# 用户数据
users = {
    'admin': {'password': 'admin123', 'role': 'admin'},
    'user': {'password': 'user123', 'role': 'user'}
}

# 用户模型
class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id, users[user_id]['role'])
    return None

# 配置 Babel，设置默认语言

app.config['BABEL_DEFAULT_LOCALE'] = 'zh'  # 默认语言
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'zh']  # 允许的语言

babel = Babel()

def get_locale():
    return session.get('lang', 'zh')  # 默认中文

babel.init_app(app, locale_selector=get_locale)

@app.route('/switch_language/<lang>')
def switch_language(lang):
    if lang in ['en', 'zh']:
        session.permanent = True
        session['lang'] = lang
    return redirect(request.referrer or url_for('dashboard'))

# 订单数据表
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(100))
    mbl_number = db.Column(db.String(100))
    hbl_number = db.Column(db.String(100))
    container_number = db.Column(db.String(100))
    pol = db.Column(db.String(100))
    etd = db.Column(db.String(100))
    booking_eta = db.Column(db.String(100))
    pod_eta = db.Column(db.String(100))
    material_code = db.Column(db.String(100))
    quantity = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 初始化数据库
with app.app_context():
    db.create_all()

# 处理 Excel 导入
def import_excel_to_db():
    excel_file = os.path.join(UPLOAD_FOLDER, 'material.xlsx')
    if os.path.exists(excel_file):
        try:
            data = pd.read_excel(excel_file, dtype=str).fillna('')  # 强制所有列为字符串
            data.columns = [col.strip().upper() for col in data.columns]  # 统一列名

            for _, row in data.iterrows():
                order = Order(
                    po_number=str(row.get('PO#', '')).strip(),
                    mbl_number=str(row.get('MBL# / MAWB#\n船东提单号', '')).strip(),
                    hbl_number=str(row.get('HBL#\n提单号', '')).strip(),
                    container_number=str(row.get('CNTR#\n柜号', '')).strip(),
                    pol=str(row.get('POL\n起运港', '')).strip(),
                    etd=str(row.get('ETD\n开船日', '')).strip(),
                    booking_eta=str(row.get('BOOKING ETA\n订舱的到港日', '')).strip(),
                    pod_eta=str(row.get('POD ETA\n实际到港日期', '')).strip(),
                    material_code=str(row.get('Material Code', '')).strip(),
                    quantity=str(row.get('Quantity', '')).strip(),
                )
                db.session.add(order)
            db.session.commit()
            flash('Data imported successfully!')
        except Exception as e:
            flash(f'Failed to import data: {str(e)}')


# 主页跳转到登录页
@app.route('/')
def home():
    return redirect(url_for('login'))

# api路由
@app.route('/api/order_status')
@login_required
def order_status():
    orders = Order.query.all()
    status_count = {}

    for order in orders:
        if order.pol in status_count:
            status_count[order.pol] += 1
        else:
            status_count[order.pol] = 1

    return jsonify(status_count)
# 用户登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            user = User(username, users[username]['role'])
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

# 用户登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 订单管理主页面（带搜索功能）
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    query_results = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    if request.method == 'POST':
        filters = []
        for field in ["po_number", "mbl_number", "hbl_number", "container_number", "pol", "etd", "booking_eta", "pod_eta", "material_code", "quantity"]:
            value = request.form.get(f'search_{field}', '').strip()
            if value:
                filters.append(getattr(Order, field).contains(value))

        query_results = Order.query.filter(*filters).all()

    return render_template('dashboard.html', orders=query_results)

# 订单编辑
@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == 'POST':
        order.po_number = request.form['po_number']
        order.mbl_number = request.form['mbl_number']
        order.hbl_number = request.form['hbl_number']
        order.container_number = request.form['container_number']
        order.pol = request.form['pol']
        order.etd = request.form['etd']
        order.booking_eta = request.form['booking_eta']
        order.pod_eta = request.form['pod_eta']
        order.material_code = request.form['material_code']
        order.quantity = request.form['quantity']
        db.session.commit()
        flash('Order updated successfully!')
        return redirect(url_for('dashboard'))
    return render_template('edit_order.html', order=order)

# 导出订单数据
@app.route('/export', methods=['GET'])
@login_required
def export_orders():
    orders = Order.query.all()
    data = {col: [getattr(order, col) for order in orders] for col in ["po_number", "mbl_number", "hbl_number", "container_number", "pol", "etd", "booking_eta", "pod_eta", "material_code", "quantity"]}
    df = pd.DataFrame(data)
    output_file = os.path.join(UPLOAD_FOLDER, 'exported_orders.xlsx')
    df.to_excel(output_file, index=False)
    return send_file(output_file, as_attachment=True)

# 文件上传（仅限管理员）
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if current_user.role != 'admin':
        flash('You do not have permission to upload files.', 'error')
        return redirect(url_for('dashboard'))

    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('dashboard'))

    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('dashboard'))

    if not file.filename.endswith('.xlsx'):
        flash('Invalid file type. Please upload an Excel file.', 'error')
        return redirect(url_for('dashboard'))

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'material.xlsx')
    file.save(file_path)

    # 运行数据导入
    try:
        import_excel_to_db()
        flash('File uploaded and data imported successfully!', 'success')
    except Exception as e:
        flash(f'Error importing file: {str(e)}', 'error')

    return redirect(url_for('dashboard'))

# 运行 Flask 应用
if __name__ == '__main__':
    app.run(debug=True, port=5000)
